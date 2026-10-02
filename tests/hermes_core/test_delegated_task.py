from __future__ import annotations

import ast
import unittest
from dataclasses import replace
from pathlib import Path

from tools.hermes_core.delegated_task import (
    CapabilityViolationError,
    DelegationIntegrityError,
    InvalidCanonicalEnvelopeError,
    LeaseExpiredError,
    build_delegated_capability_lease,
    build_delegated_task_envelope,
    reconstruct_capability_lease,
    reconstruct_delegated_task,
    validate_capability_request,
)


H = "a" * 64


def envelope(**overrides):
    values = {
        "delegation_revision": 0,
        "originator_request_id": "request-1",
        "task_id": "task-1",
        "parent_task_id": None,
        "originator_agent_id": "hermes-originator",
        "requested_target_agent_id": "codex-cli-agent",
        "operation": "write_report",
        "objective": "Produce the bounded report.",
        "instructions": "Use only the declared inputs.",
        "input_manifest": [
            {
                "ordinal": 0,
                "reference_type": "workspace_file",
                "reference": "inputs/source.txt",
                "sha256": H,
                "media_type": "text/plain",
            }
        ],
        "scope": {
            "read_paths": ["inputs/source.txt"],
            "write_paths": ["outputs/report.json"],
            "allowed_tools": ["read_file", "write_file"],
            "network_policy": "deny",
            "approved_hosts": [],
            "time_budget_seconds": 300,
        },
        "expected_result_schema_id": "schema://report/v1",
        "expected_evidence": [
            {"ordinal": 0, "evidence_type": "output_sha256"}
        ],
        "requested_at": "2026-08-27T12:00:00Z",
        "expires_at": "2026-08-27T13:00:00Z",
        "redelegation_allowed": False,
    }
    values.update(overrides)
    return build_delegated_task_envelope(**values)


def lease(task=None, **overrides):
    task = task or envelope()
    values = {
        "delegation_id": task.delegation_id,
        "delegated_task_hash": task.artifact_hash,
        "authorization_id": "authorization-1",
        "authorization_hash": "b" * 64,
        "attempt_id": "attempt-1",
        "attempt_hash": "c" * 64,
        "route_id": "route-1",
        "route_hash": "d" * 64,
        "recipient_agent_id": task.requested_target_agent_id,
        "worker_descriptor_hash": "e" * 64,
        "allowed_operation": task.operation,
        "allowed_tools": ["read_file", "write_file"],
        "prohibited_tools": ["shell"],
        "permitted_read_paths": ["inputs/source.txt"],
        "permitted_write_paths": ["outputs/report.json"],
        "network_policy": "deny",
        "approved_hosts": [],
        "max_runtime_seconds": 120,
        "expected_result_schema_id": task.expected_result_schema_id,
        "expected_evidence": task.expected_evidence,
        "issued_at": "2026-08-27T12:00:00Z",
        "not_before": "2026-08-27T12:00:00Z",
        "expires_at": "2026-08-27T12:10:00Z",
        "redelegation_allowed": False,
    }
    values.update(overrides)
    return build_delegated_capability_lease(**values)


class DelegatedTaskCanonicalTests(unittest.TestCase):
    def test_same_material_is_deterministic(self):
        left = envelope()
        right = envelope()
        self.assertEqual(left.delegation_id, right.delegation_id)
        self.assertEqual(left.task_input_hash, right.task_input_hash)
        self.assertEqual(left.artifact_hash, right.artifact_hash)
        self.assertEqual(left.canonical_json(), right.canonical_json())

    def test_mapping_and_set_input_order_do_not_change_hashes(self):
        scope = {
            "approved_hosts": [],
            "network_policy": "deny",
            "allowed_tools": ["write_file", "read_file", "read_file"],
            "write_paths": ["outputs/report.json"],
            "read_paths": ["inputs/source.txt"],
            "time_budget_seconds": 300,
        }
        self.assertEqual(envelope().artifact_hash, envelope(scope=scope).artifact_hash)

    def test_ordered_records_are_sorted_by_explicit_ordinal(self):
        evidence = [
            {"ordinal": 1, "evidence_type": "summary"},
            {"ordinal": 0, "evidence_type": "output_sha256"},
        ]
        task = envelope(expected_evidence=evidence)
        self.assertEqual([item["ordinal"] for item in task.expected_evidence], [0, 1])

    def test_noncontiguous_ordinals_fail_closed(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            envelope(expected_evidence=[{"ordinal": 1, "evidence_type": "x"}])

    def test_changed_task_material_changes_task_and_artifact_hash(self):
        left = envelope()
        right = envelope(objective="Produce a different bounded report.")
        self.assertEqual(left.delegation_id, right.delegation_id)
        self.assertNotEqual(left.task_input_hash, right.task_input_hash)
        self.assertNotEqual(left.artifact_hash, right.artifact_hash)

    def test_changed_scope_is_not_task_identity_but_changes_integrity_hash(self):
        left = envelope()
        changed = dict(left.scope.to_canonical_dict())
        changed["time_budget_seconds"] = 200
        right = envelope(scope=changed)
        self.assertEqual(left.delegation_id, right.delegation_id)
        self.assertEqual(left.task_input_hash, right.task_input_hash)
        self.assertNotEqual(left.artifact_hash, right.artifact_hash)

    def test_changed_timestamp_is_metadata_not_task_identity(self):
        left = envelope()
        right = envelope(
            requested_at="2026-08-27T12:01:00Z",
            expires_at="2026-08-27T13:01:00Z",
        )
        self.assertEqual(left.delegation_id, right.delegation_id)
        self.assertEqual(left.task_input_hash, right.task_input_hash)
        self.assertNotEqual(left.artifact_hash, right.artifact_hash)

    def test_changed_target_changes_artifact_only(self):
        left = envelope()
        right = envelope(requested_target_agent_id="other-agent")
        self.assertEqual(left.delegation_id, right.delegation_id)
        self.assertEqual(left.task_input_hash, right.task_input_hash)
        self.assertNotEqual(left.artifact_hash, right.artifact_hash)

    def test_explicit_null_is_present(self):
        payload = envelope(expires_at=None).to_canonical_dict()
        self.assertIn("parent_task_id", payload)
        self.assertIn("expires_at", payload)
        self.assertIsNone(payload["parent_task_id"])
        self.assertIsNone(payload["expires_at"])

    def test_relative_paths_are_host_independent_and_absolute_paths_rejected(self):
        self.assertEqual(envelope().input_manifest[0]["reference"], "inputs/source.txt")
        bad_manifest = [
            {
                "ordinal": 0,
                "reference_type": "workspace_file",
                "reference": "C:/Users/A/source.txt",
                "sha256": H,
                "media_type": "text/plain",
            }
        ]
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            envelope(input_manifest=bad_manifest)

    def test_content_addressed_reference_must_match_digest(self):
        manifest = [
            {
                "ordinal": 0,
                "reference_type": "content_addressed",
                "reference": f"sha256:{H}",
                "sha256": H,
                "media_type": "text/plain",
            }
        ]
        self.assertEqual(envelope(input_manifest=manifest).input_manifest[0]["reference"], f"sha256:{H}")
        manifest[0]["reference"] = f"sha256:{'f' * 64}"
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            envelope(input_manifest=manifest)

    def test_float_binary_and_trailing_whitespace_rejected(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            envelope(expected_evidence=[{"ordinal": 0, "score": 1.25}])
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            envelope(expected_evidence=[{"ordinal": 0, "data": b"x"}])
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            envelope(objective="bad ")

    def test_line_endings_normalize_before_hashing(self):
        self.assertEqual(
            envelope(instructions="line one\r\nline two").artifact_hash,
            envelope(instructions="line one\nline two").artifact_hash,
        )

    def test_redelegation_fails_closed(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            envelope(redelegation_allowed=True)

    def test_reconstruction_verifies_all_hashes(self):
        task = envelope()
        self.assertEqual(reconstruct_delegated_task(task.to_canonical_dict()), task)
        tampered = task.to_canonical_dict()
        tampered["objective"] = "tampered"
        with self.assertRaises(DelegationIntegrityError):
            reconstruct_delegated_task(tampered)


class CapabilityLeaseTests(unittest.TestCase):
    def test_frozen_identity_domains_are_distinct(self):
        task = envelope()
        artifact = lease(task)
        identities = {
            task.delegation_id,
            task.task_input_hash,
            artifact.lease_id,
            artifact.authorization_id,
            artifact.attempt_id,
            "launch-attempt-1",
            "runtime-1",
            "receiver-acceptance-1",
            "result-1",
        }
        self.assertEqual(len(identities), 9)

    def test_lease_identity_and_hash_are_deterministic(self):
        left = lease()
        right = lease()
        self.assertEqual(left.lease_id, right.lease_id)
        self.assertEqual(left.artifact_hash, right.artifact_hash)

    def test_lease_identity_binds_attempt_and_route(self):
        self.assertNotEqual(lease().lease_id, lease(route_id="route-2").lease_id)
        self.assertNotEqual(lease().lease_id, lease(attempt_id="attempt-2").lease_id)

    def test_lease_reconstruction_verifies_integrity(self):
        artifact = lease()
        self.assertEqual(reconstruct_capability_lease(artifact.to_canonical_dict()), artifact)
        tampered = artifact.to_canonical_dict()
        tampered["recipient_agent_id"] = "wrong-agent"
        with self.assertRaises(DelegationIntegrityError):
            reconstruct_capability_lease(tampered)

    def test_wrong_recipient_delegation_and_operation_rejected(self):
        artifact = lease()
        common = dict(
            tools=[], read_paths=[], write_paths=[], network_hosts=[],
            at="2026-08-27T12:05:00Z",
        )
        for field, value in (
            ("recipient_agent_id", "wrong-agent"),
            ("delegation_id", "delegation-wrong"),
            ("operation", "wrong-operation"),
        ):
            args = {
                "recipient_agent_id": artifact.recipient_agent_id,
                "delegation_id": artifact.delegation_id,
                "operation": artifact.allowed_operation,
                **common,
            }
            args[field] = value
            with self.subTest(field=field), self.assertRaises(CapabilityViolationError):
                validate_capability_request(artifact, **args)

    def test_tool_path_and_network_escalation_rejected(self):
        artifact = lease()
        base = dict(
            recipient_agent_id=artifact.recipient_agent_id,
            delegation_id=artifact.delegation_id,
            operation=artifact.allowed_operation,
            at="2026-08-27T12:05:00Z",
        )
        for extra in (
            {"tools": ["shell"]},
            {"read_paths": ["secrets/key.txt"]},
            {"write_paths": ["outside/result.txt"]},
            {"network_hosts": ["example.com"]},
        ):
            with self.subTest(extra=extra), self.assertRaises(CapabilityViolationError):
                validate_capability_request(artifact, **base, **extra)

    def test_valid_bounded_capability_passes(self):
        artifact = lease()
        validate_capability_request(
            artifact,
            recipient_agent_id=artifact.recipient_agent_id,
            delegation_id=artifact.delegation_id,
            operation=artifact.allowed_operation,
            tools=["read_file"],
            read_paths=["inputs/source.txt"],
            write_paths=["outputs/report.json"],
            at="2026-08-27T12:05:00Z",
        )

    def test_expired_lease_rejected(self):
        artifact = lease()
        with self.assertRaises(LeaseExpiredError):
            validate_capability_request(
                artifact,
                recipient_agent_id=artifact.recipient_agent_id,
                delegation_id=artifact.delegation_id,
                operation=artifact.allowed_operation,
                at=artifact.expires_at,
            )

    def test_invalid_lease_time_order_and_overlap_rejected(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            lease(not_before="2026-08-27T12:11:00Z")
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            lease(allowed_tools=["shell"], prohibited_tools=["shell"])

    def test_mutated_dataclass_fails_hash_verification(self):
        artifact = replace(lease(), recipient_agent_id="wrong-agent")
        with self.assertRaises(DelegationIntegrityError):
            artifact.verify_hash()


class NegativeCapabilitySourceTests(unittest.TestCase):
    def test_r12a_production_modules_have_no_forbidden_imports_or_calls(self):
        root = Path(__file__).resolve().parents[2]
        forbidden_import_roots = {
            "subprocess", "socket", "requests", "httpx", "urllib",
            "playwright", "selenium", "mcp", "apscheduler", "torch", "diffusers",
        }
        forbidden_text = {
            "codex", "kilo", "comfyui", "studio bible", "regional hand repair",
            "image pipeline", "create_subprocess", "popen", "shell=true",
        }
        for relative in (
            "tools/hermes_core/delegated_task.py",
            "tools/hermes_core/sqlite_delegation_store.py",
        ):
            source = (root / relative).read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
            self.assertFalse(imports & forbidden_import_roots, relative)
            lowered = source.lower()
            for token in forbidden_text:
                self.assertNotIn(token, lowered, f"{relative}: {token}")


if __name__ == "__main__":
    unittest.main()
