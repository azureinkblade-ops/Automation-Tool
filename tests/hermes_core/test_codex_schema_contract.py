"""R12E-R5 result-schema qualification tests. No live process is available."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from jsonschema import Draft202012Validator, ValidationError

from tests.hermes_core.run_r12e_live_proof import _schema
from tools.hermes_core.codex_adapter import (
    PINNED_CODEX_VERSION,
    CodexReceiverAdapter,
    CodexSchemaQualificationError,
    CodexTrustedConfig,
    codex_cli_contract,
    codex_cli_contract_id,
    qualify_codex_result_schema_file,
    qualify_codex_result_schema_material,
)


TASK_HASH = "d0116ebcb0bdfe89960a12345871c54d064bb81e76a56112d8ee32f02fd7463c"
RECEIPT_HASH = "d03816c318b4d39b79be8ae9b1babcf148367013e03c7aeff5eb7e6a49191f86"
FAILED_R12E_R4_FILE_SHA256 = "51548a8306b76e273a83f0dfc22c687aae8ede6722d5aa0a4998234983634887"


def failed_r12e_r4_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "additionalProperties": False,
        "required": [
            "schema_version", "outcome", "result_payload", "output_manifest",
            "evidence_manifest", "error_code", "error_summary",
        ],
        "properties": {
            "schema_version": {"const": "1"},
            "outcome": {"const": "SUCCEEDED"},
            "result_payload": {
                "type": "object", "additionalProperties": False,
                "required": ["qualification_statement", "task_input_hash"],
                "properties": {
                    "qualification_statement": {
                        "const": "EA-4D.4F R12E governed delegation proof complete."
                    },
                    "task_input_hash": {"const": TASK_HASH},
                },
            },
            "output_manifest": {"type": "array", "maxItems": 0},
            "evidence_manifest": {
                "type": "array", "minItems": 1, "maxItems": 1,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["ordinal", "evidence_type", "sha256"],
                    "properties": {
                        "ordinal": {"const": 0},
                        "evidence_type": {"const": "receiver_acceptance_sha256"},
                        "sha256": {"const": RECEIPT_HASH},
                    },
                },
            },
            "error_code": {"type": "null"},
            "error_summary": {"type": "null"},
        },
    }


def intended_result() -> dict:
    return {
        "schema_version": "1",
        "outcome": "SUCCEEDED",
        "result_payload": {
            "qualification_statement": "EA-4D.4F R12E governed delegation proof complete.",
            "task_input_hash": TASK_HASH,
        },
        "output_manifest": [],
        "evidence_manifest": [{
            "ordinal": 0,
            "evidence_type": "receiver_acceptance_sha256",
            "sha256": RECEIPT_HASH,
        }],
        "error_code": None,
        "error_summary": None,
    }


class SchemaFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.executable = self.root / "codex.exe"
        self.executable.write_bytes(b"schema qualification fixture")
        (self.root / "work").mkdir()
        (self.root / "runtime").mkdir()
        self.schema_file = self.root / "runtime" / "schema.json"
        self.schema = _schema(TASK_HASH, RECEIPT_HASH)
        self.write_schema(self.schema)
        binary_hash = hashlib.sha256(self.executable.read_bytes()).hexdigest()
        self.config = CodexTrustedConfig(
            executable_path=str(self.executable),
            expected_sha256=binary_hash,
            expected_version=PINNED_CODEX_VERSION,
            fixture_root=str(self.root),
            working_directory=str(self.root / "work"),
            output_schema_file=str(self.schema_file),
            spool_directory=str(self.root / "runtime" / "spool"),
            registry_path=str(self.root / "runtime" / "transport.sqlite3"),
            environment=(("CODEX_HOME", str(self.root / "codex-home")),),
            expected_cli_contract_id=codex_cli_contract_id(
                codex_cli_contract(binary_hash, PINNED_CODEX_VERSION)
            ),
            expected_schema_sha256=qualify_codex_result_schema_material(self.schema).schema_sha256,
        )
        self.process = Mock()

    def tearDown(self):
        self.tmp.cleanup()

    def write_schema(self, schema):
        self.schema_file.write_text(
            json.dumps(schema, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def probe(self, *_):
        return 0, PINNED_CODEX_VERSION, ""

    def adapter(self, config=None):
        return CodexReceiverAdapter(
            config=config or self.config,
            process_impl=self.process,
            version_probe=self.probe,
        )

    def prepare(self, config=None):
        return self.adapter(config).prepare_invocation(
            idempotency_key="schema-idem",
            launch_attempt_id="schema-launch",
            delegation_id="schema-delegation",
            stdin_data='{"task":"qualification-only"}',
        )


class HistoricalFailureTests(SchemaFixture):
    def test_exact_r12e_r4_schema_bytes_are_recovered(self):
        canonical = json.dumps(failed_r12e_r4_schema(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.assertEqual(hashlib.sha256((canonical + "\r\n").encode()).hexdigest(), FAILED_R12E_R4_FILE_SHA256)

    def test_exact_r12e_r4_schema_fails_before_process_capability(self):
        self.write_schema(failed_r12e_r4_schema())
        invalid_hash = hashlib.sha256(
            json.dumps(failed_r12e_r4_schema(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.assertRaisesRegex(CodexSchemaQualificationError, "explicit supported type"):
            self.prepare(replace(self.config, expected_schema_sha256=invalid_hash))
        self.assertEqual(self.process.start.call_count, 0)


class CompatibilityAuditTests(SchemaFixture):
    def test_corrected_fixture_is_fully_qualified(self):
        qualification = qualify_codex_result_schema_file(self.schema_file)
        self.assertEqual(qualification.schema_sha256, self.config.expected_schema_sha256)

    def test_string_boolean_and_integer_constants_require_matching_types(self):
        for schema in (
            {"type": "string", "const": "x"},
            {"type": "boolean", "const": True},
            {"type": "integer", "const": 1},
        ):
            self.assertTrue(qualify_codex_result_schema_material(schema).qualification_id)
        with self.assertRaises(CodexSchemaQualificationError):
            qualify_codex_result_schema_material({"type": "integer", "const": True})

    def test_const_without_type_is_rejected(self):
        with self.assertRaisesRegex(CodexSchemaQualificationError, "explicit supported type"):
            qualify_codex_result_schema_material({"const": "x"})

    def test_every_object_property_must_be_required_and_closed(self):
        schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": []}
        with self.assertRaises(CodexSchemaQualificationError):
            qualify_codex_result_schema_material(schema)

    def test_array_items_are_required_even_when_max_items_is_zero(self):
        with self.assertRaisesRegex(CodexSchemaQualificationError, "items is required"):
            qualify_codex_result_schema_material({"type": "array", "maxItems": 0})

    def test_enum_requires_explicit_matching_type(self):
        qualify_codex_result_schema_material({"type": "string", "enum": ["a", "b"]})
        with self.assertRaises(CodexSchemaQualificationError):
            qualify_codex_result_schema_material({"type": "string", "enum": ["a", 1]})

    def test_unsupported_composition_fails_closed(self):
        with self.assertRaisesRegex(CodexSchemaQualificationError, "unsupported"):
            qualify_codex_result_schema_material({"type": "string", "anyOf": []})


class SemanticEquivalenceTests(SchemaFixture):
    def assert_rejected(self, mutation):
        value = intended_result()
        mutation(value)
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(value)

    def test_intended_result_remains_accepted(self):
        Draft202012Validator(self.schema).validate(intended_result())

    def test_wrong_constant_value_rejected(self):
        self.assert_rejected(lambda value: value.update(outcome="FAILED"))

    def test_wrong_constant_type_rejected(self):
        self.assert_rejected(lambda value: value["evidence_manifest"][0].update(ordinal="0"))

    def test_missing_required_property_rejected(self):
        self.assert_rejected(lambda value: value.pop("schema_version"))

    def test_extra_property_rejected(self):
        self.assert_rejected(lambda value: value.update(extra="widened"))

    def test_malformed_evidence_rejected(self):
        self.assert_rejected(lambda value: value["evidence_manifest"][0].update(sha256="wrong"))

    def test_nonempty_output_scope_rejected(self):
        self.assert_rejected(lambda value: value["output_manifest"].append({}))


class IdentityAndEligibilityTests(SchemaFixture):
    def test_same_schema_material_has_same_hash_and_qualification(self):
        first = qualify_codex_result_schema_material(self.schema)
        second = qualify_codex_result_schema_material(json.loads(json.dumps(self.schema)))
        self.assertEqual(first, second)

    def test_corrected_material_has_new_identity_from_failed_schema(self):
        corrected = qualify_codex_result_schema_material(self.schema)
        failed_canonical = json.dumps(failed_r12e_r4_schema(), sort_keys=True, separators=(",", ":"))
        self.assertNotEqual(corrected.schema_sha256, hashlib.sha256(failed_canonical.encode()).hexdigest())

    def test_significant_mutation_changes_hash(self):
        changed = json.loads(json.dumps(self.schema))
        changed["properties"]["outcome"]["const"] = "FAILED"
        self.assertNotEqual(
            qualify_codex_result_schema_material(self.schema).schema_sha256,
            qualify_codex_result_schema_material(changed).schema_sha256,
        )

    def test_unqualified_schema_is_not_invocation_eligible(self):
        with self.assertRaisesRegex(CodexSchemaQualificationError, "required"):
            self.prepare(replace(self.config, expected_schema_sha256=None))
        self.assertEqual(self.process.start.call_count, 0)

    def test_schema_hash_mismatch_is_not_invocation_eligible(self):
        with self.assertRaisesRegex(CodexSchemaQualificationError, "hash differs"):
            self.prepare(replace(self.config, expected_schema_sha256="0" * 64))
        self.assertEqual(self.process.start.call_count, 0)

    def test_schema_drift_is_not_invocation_eligible(self):
        changed = json.loads(json.dumps(self.schema))
        changed["properties"]["outcome"]["const"] = "FAILED"
        self.write_schema(changed)
        with self.assertRaisesRegex(CodexSchemaQualificationError, "hash differs"):
            self.prepare()
        self.assertEqual(self.process.start.call_count, 0)

    def test_valid_qualified_schema_is_preparable_without_process(self):
        record, _, replayed = self.prepare()
        self.assertEqual(record.start_state, "PREPARED")
        self.assertFalse(replayed)
        self.assertEqual(self.process.start.call_count, 0)

    def test_prepared_record_remains_ineligible_after_schema_drift(self):
        self.prepare()
        changed = json.loads(json.dumps(self.schema))
        changed["properties"]["outcome"]["const"] = "FAILED"
        self.write_schema(changed)
        with self.assertRaisesRegex(CodexSchemaQualificationError, "hash differs"):
            self.prepare()
        self.assertEqual(self.process.start.call_count, 0)

    def test_terminal_record_replay_does_not_requalify_historical_schema(self):
        record, _, _ = self.prepare()
        adapter = self.adapter()
        adapter.registry.transition(
            record.idempotency_key,
            start_state="DEFINITELY_STARTED",
            terminal_state="FAILED",
            pid=9,
            result_json='{"historical":true}',
        )
        self.write_schema(failed_r12e_r4_schema())
        replay, _, replayed = self.prepare()
        self.assertTrue(replayed)
        self.assertEqual(replay.terminal_state, "FAILED")
        self.assertEqual(self.process.start.call_count, 0)


if __name__ == "__main__":
    unittest.main()
