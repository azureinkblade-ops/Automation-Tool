"""R12E-R6B instance-bound result-schema qualification tests."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from tools.hermes_core.codex_adapter import (
    ArgvConstructionError,
    CodexReceiverAdapter,
    CodexSchemaQualificationError,
    CodexTrustedConfig,
    codex_cli_contract,
    codex_cli_contract_id,
    qualify_codex_result_schema_material,
)
from tools.hermes_core.codex_result_schema import (
    INSTANCE_QUALIFICATION_VERSION,
    STRUCTURAL_POLICY_ID,
    CodexInstanceSchemaError,
    CodexResultSchemaLineage,
    build_instance_bound_result_schema,
    qualify_instance_bound_result_schema,
    qualify_instance_bound_result_schema_file,
    structural_policy_id,
    structural_policy_material,
)


LINEAGE_A = CodexResultSchemaLineage("a" * 64, "b" * 64)
LINEAGE_B = CodexResultSchemaLineage("c" * 64, "d" * 64)
HISTORICAL_R4_LINEAGE = CodexResultSchemaLineage(
    "d0116ebcb0bdfe89960a12345871c54d064bb81e76a56112d8ee32f02fd7463c",
    "d03816c318b4d39b79be8ae9b1babcf148367013e03c7aeff5eb7e6a49191f86",
)
HISTORICAL_R5_SCHEMA_SHA256 = "b2d9872bb704cbe4a65619b70f938a13e1b4941ba82e4256eec717a4733902fe"
BINARY_A = "1" * 64
BINARY_B = "2" * 64
VERSION = "codex-cli test"
CLI_A = "3" * 64
CLI_B = "4" * 64


def qualify(lineage=LINEAGE_A, schema=None, **changes):
    values = {
        "lineage": lineage,
        "binary_sha256": BINARY_A,
        "binary_version": VERSION,
        "cli_contract_id": CLI_A,
        "expected_structural_policy_id": STRUCTURAL_POLICY_ID,
    }
    values.update(changes)
    return qualify_instance_bound_result_schema(
        build_instance_bound_result_schema(lineage) if schema is None else schema,
        **values,
    )


class StructuralPolicyTests(unittest.TestCase):
    def test_policy_identity_is_deterministic(self):
        self.assertEqual(structural_policy_id(), structural_policy_id())
        self.assertEqual(structural_policy_id(), STRUCTURAL_POLICY_ID)

    def test_policy_identity_does_not_depend_on_instance_lineage(self):
        self.assertEqual(qualify(LINEAGE_A).structural_policy_id, qualify(LINEAGE_B).structural_policy_id)

    def test_structural_mutation_changes_policy_identity(self):
        changed = copy.deepcopy(structural_policy_material())
        changed["schema_template"]["properties"]["output_manifest"]["maxItems"] = 1
        self.assertNotEqual(structural_policy_id(changed), STRUCTURAL_POLICY_ID)

    def test_parameter_allowlist_has_canonical_durable_sources(self):
        parameters = structural_policy_material()["instance_parameters"]
        self.assertEqual(set(parameters), {"task_input_hash", "receiver_receipt_hash"})
        self.assertEqual(parameters["task_input_hash"]["source"], "canonical_delegated_task.task_input_hash")
        self.assertEqual(parameters["receiver_receipt_hash"]["source"], "durable_delegation_receipt.artifact_hash")

    def test_unknown_parameter_is_rejected_by_closed_function_signature(self):
        with self.assertRaises(TypeError):
            qualify_instance_bound_result_schema(
                build_instance_bound_result_schema(LINEAGE_A),
                lineage=LINEAGE_A, binary_sha256=BINARY_A, binary_version=VERSION,
                cli_contract_id=CLI_A, unknown_lineage="x",
            )


class InstanceSchemaTests(unittest.TestCase):
    def test_exact_lineage_is_substituted_at_frozen_paths(self):
        schema = build_instance_bound_result_schema(LINEAGE_A)
        properties = schema["properties"]
        self.assertEqual(
            properties["result_payload"]["properties"]["task_input_hash"]["const"],
            LINEAGE_A.task_input_hash,
        )
        self.assertEqual(
            properties["evidence_manifest"]["items"]["properties"]["sha256"]["const"],
            LINEAGE_A.receiver_receipt_hash,
        )

    def test_same_lineage_produces_identical_schema_bytes(self):
        first = json.dumps(build_instance_bound_result_schema(LINEAGE_A), sort_keys=True, separators=(",", ":"))
        second = json.dumps(build_instance_bound_result_schema(LINEAGE_A), sort_keys=True, separators=(",", ":"))
        self.assertEqual(first, second)

    def test_closed_lineage_type_is_required(self):
        with self.assertRaises(CodexInstanceSchemaError):
            build_instance_bound_result_schema({"task_input_hash": "a" * 64})

    def test_missing_lineage_is_rejected(self):
        with self.assertRaises(TypeError):
            CodexResultSchemaLineage(task_input_hash="a" * 64)

    def test_invalid_or_noncanonical_hash_is_rejected(self):
        for value in ("short", "z" * 64, "A" * 64):
            with self.subTest(value=value[:5]):
                with self.assertRaises(CodexInstanceSchemaError):
                    CodexResultSchemaLineage(value, "b" * 64)

    def test_different_lineage_changes_schema_hash_but_not_policy(self):
        first, second = qualify(LINEAGE_A), qualify(LINEAGE_B)
        self.assertEqual(first.structural_policy_id, second.structural_policy_id)
        self.assertNotEqual(first.instance_schema_sha256, second.instance_schema_sha256)
        self.assertNotEqual(first.instance_lineage_hash, second.instance_lineage_hash)

    def test_different_lineage_changes_instance_qualification(self):
        self.assertNotEqual(qualify(LINEAGE_A).qualification_id, qualify(LINEAGE_B).qualification_id)

    def test_same_inputs_produce_same_qualification(self):
        self.assertEqual(qualify(LINEAGE_A), qualify(LINEAGE_A))
        self.assertEqual(qualify(LINEAGE_A).qualification_version, INSTANCE_QUALIFICATION_VERSION)


class CrossInstanceProtectionTests(unittest.TestCase):
    def test_instance_a_schema_is_rejected_for_instance_b(self):
        with self.assertRaisesRegex(CodexInstanceSchemaError, "durable lineage"):
            qualify(LINEAGE_B, schema=build_instance_bound_result_schema(LINEAGE_A))

    def test_historical_r4_style_schema_cannot_be_reused_for_fresh_lineage(self):
        historical = build_instance_bound_result_schema(HISTORICAL_R4_LINEAGE)
        self.assertEqual(
            qualify(HISTORICAL_R4_LINEAGE, schema=historical).instance_schema_sha256,
            HISTORICAL_R5_SCHEMA_SHA256,
        )
        with self.assertRaises(CodexInstanceSchemaError):
            qualify(LINEAGE_B, schema=historical)

    def test_schema_byte_drift_is_rejected(self):
        changed = build_instance_bound_result_schema(LINEAGE_A)
        changed["properties"]["outcome"]["const"] = "FAILED"
        with self.assertRaises(CodexInstanceSchemaError):
            qualify(LINEAGE_A, schema=changed)

    def test_structural_policy_mismatch_is_rejected(self):
        with self.assertRaisesRegex(CodexInstanceSchemaError, "policy ID mismatch"):
            qualify(LINEAGE_A, expected_structural_policy_id="0" * 64)

    def test_binary_environment_mismatch_changes_and_rejects_qualification(self):
        expected = qualify(LINEAGE_A).qualification_id
        with self.assertRaisesRegex(CodexInstanceSchemaError, "qualification ID mismatch"):
            qualify(LINEAGE_A, binary_sha256=BINARY_B, expected_qualification_id=expected)

    def test_cli_environment_mismatch_changes_and_rejects_qualification(self):
        expected = qualify(LINEAGE_A).qualification_id
        with self.assertRaisesRegex(CodexInstanceSchemaError, "qualification ID mismatch"):
            qualify(LINEAGE_A, cli_contract_id=CLI_B, expected_qualification_id=expected)


class EligibilityFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.executable = self.root / "codex.exe"
        self.executable.write_bytes(b"r6b fake codex")
        (self.root / "work").mkdir()
        (self.root / "runtime").mkdir()
        self.schema_file = self.root / "runtime" / "schema.json"
        self.schema = build_instance_bound_result_schema(LINEAGE_A)
        self.schema_file.write_text(json.dumps(self.schema), encoding="utf-8")
        binary_hash = hashlib.sha256(self.executable.read_bytes()).hexdigest()
        cli_id = codex_cli_contract_id(codex_cli_contract(binary_hash, VERSION))
        instance = qualify_instance_bound_result_schema(
            self.schema, lineage=LINEAGE_A, binary_sha256=binary_hash,
            binary_version=VERSION, cli_contract_id=cli_id,
        )
        self.config = CodexTrustedConfig(
            executable_path=str(self.executable), expected_sha256=binary_hash,
            expected_version=VERSION, fixture_root=str(self.root),
            working_directory=str(self.root / "work"),
            output_schema_file=str(self.schema_file),
            spool_directory=str(self.root / "runtime" / "spool"),
            registry_path=str(self.root / "runtime" / "transport.sqlite3"),
            environment=(("CODEX_HOME", str(self.root / "codex-home")),),
            expected_cli_contract_id=cli_id,
            expected_schema_sha256=qualify_codex_result_schema_material(self.schema).schema_sha256,
            require_instance_schema_qualification=True,
            expected_structural_policy_id=STRUCTURAL_POLICY_ID,
            expected_instance_schema_qualification_id=instance.qualification_id,
            expected_task_input_hash=LINEAGE_A.task_input_hash,
            expected_receiver_receipt_hash=LINEAGE_A.receiver_receipt_hash,
        )
        self.process = Mock()

    def tearDown(self):
        self.tmp.cleanup()

    def adapter(self, config=None):
        return CodexReceiverAdapter(
            config=config or self.config,
            process_impl=self.process,
            version_probe=lambda *_: (0, VERSION, ""),
            parser_probe=lambda *_: (0, "Usage: codex exec [OPTIONS] [PROMPT]", ""),
        )

    def prepare(self, config=None):
        return self.adapter(config).prepare_invocation(
            idempotency_key="r6b-idem", launch_attempt_id="r6b-launch",
            delegation_id="r6b-delegation", stdin_data='{"qualification":"fake"}',
        )


class EligibilityTests(EligibilityFixture):
    def test_fully_qualified_fake_instance_is_preparable_without_process(self):
        record, _, replayed = self.prepare()
        self.assertEqual(record.start_state, "PREPARED")
        self.assertFalse(replayed)
        self.assertEqual(self.process.start.call_count, 0)

    def test_incomplete_identity_binding_rejected_before_process(self):
        config = replace(self.config, expected_receiver_receipt_hash=None)
        with self.assertRaises(CodexSchemaQualificationError):
            self.adapter(config)
        self.assertEqual(self.process.start.call_count, 0)

    def test_schema_absent_is_rejected_before_process(self):
        self.schema_file.unlink()
        with self.assertRaises(CodexSchemaQualificationError):
            self.prepare()
        self.assertEqual(self.process.start.call_count, 0)

    def test_schema_binding_without_enforcement_is_rejected(self):
        config = replace(self.config, require_instance_schema_qualification=False)
        with self.assertRaises(CodexSchemaQualificationError):
            self.adapter(config)
        self.assertEqual(self.process.start.call_count, 0)

    def test_schema_qualified_for_wrong_instance_is_rejected(self):
        config = replace(
            self.config,
            expected_task_input_hash=LINEAGE_B.task_input_hash,
            expected_receiver_receipt_hash=LINEAGE_B.receiver_receipt_hash,
        )
        with self.assertRaises(CodexSchemaQualificationError):
            self.prepare(config)
        self.assertEqual(self.process.start.call_count, 0)

    def test_qualification_id_drift_is_rejected(self):
        config = replace(self.config, expected_instance_schema_qualification_id="0" * 64)
        with self.assertRaisesRegex(CodexSchemaQualificationError, "qualification ID mismatch"):
            self.prepare(config)
        self.assertEqual(self.process.start.call_count, 0)

    def test_same_durable_instance_reopens_to_same_schema_and_qualification(self):
        first = self.adapter().qualify_instance_schema_contract()
        second = qualify_instance_bound_result_schema_file(
            self.schema_file, lineage=LINEAGE_A,
            binary_sha256=self.config.expected_sha256,
            binary_version=VERSION,
            cli_contract_id=self.config.expected_cli_contract_id,
            expected_structural_policy_id=STRUCTURAL_POLICY_ID,
            expected_qualification_id=first.qualification_id,
        )
        self.assertEqual(first, second)
        self.assertEqual(self.process.start.call_count, 0)


if __name__ == "__main__":
    unittest.main()
