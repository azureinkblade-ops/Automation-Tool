from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from tools.hermes_core.delegated_task import (
    CancellationConflictError,
    CapabilityViolationError,
    DelegationConflictError,
    DelegationIntegrityError,
    DelegationNotFoundError,
    InvalidDelegationStateTransitionError,
    LeaseConflictError,
    LeaseExpiredError,
    LeaseRevokedError,
    build_delegated_capability_lease,
    build_delegated_task_envelope,
)
from tools.hermes_core.sqlite_delegation_store import (
    DelegationStoreSchemaError,
    SQLiteDelegationStore,
)


H = "a" * 64


def make_envelope(**overrides):
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
        "input_manifest": [{
            "ordinal": 0,
            "reference_type": "workspace_file",
            "reference": "inputs/source.txt",
            "sha256": H,
            "media_type": "text/plain",
        }],
        "scope": {
            "read_paths": ["inputs/source.txt"],
            "write_paths": ["outputs/report.json"],
            "allowed_tools": ["read_file", "write_file"],
            "network_policy": "deny",
            "approved_hosts": [],
            "time_budget_seconds": 300,
        },
        "expected_result_schema_id": "schema://report/v1",
        "expected_evidence": [{"ordinal": 0, "evidence_type": "output_sha256"}],
        "requested_at": "2026-08-27T12:00:00Z",
        "expires_at": "2026-08-27T13:00:00Z",
        "redelegation_allowed": False,
    }
    values.update(overrides)
    return build_delegated_task_envelope(**values)


def make_lease(task=None, **overrides):
    task = task or make_envelope()
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


class SQLiteDelegationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "delegations.db"
        self.store = SQLiteDelegationStore(self.db)
        self.task = make_envelope()

    def tearDown(self):
        self.temp.cleanup()

    def test_fresh_database_is_latest_schema(self):
        with closing(sqlite3.connect(self.db)) as connection:
            version = connection.execute(
                "SELECT version FROM delegation_schema_version WHERE singleton=1"
            ).fetchone()[0]
        self.assertEqual(version, 2)

    def test_reopen_latest_database_does_not_change_file(self):
        before = self.db.stat().st_mtime_ns
        SQLiteDelegationStore(self.db)
        self.assertEqual(self.db.stat().st_mtime_ns, before)

    def test_unknown_schema_version_fails_closed(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE delegation_schema_version SET version=99")
            connection.commit()
        with self.assertRaises(DelegationStoreSchemaError):
            SQLiteDelegationStore(self.db)

    def test_create_read_and_replay_delegation(self):
        created = self.store.create_delegation(self.task)
        replayed = self.store.create_delegation(self.task)
        self.assertEqual(created, replayed)
        self.assertEqual(self.store.get_delegation(self.task.delegation_id), self.task)
        with closing(sqlite3.connect(self.db)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM delegations").fetchone()[0]
        self.assertEqual(count, 1)

    def test_same_identity_divergent_envelope_conflicts(self):
        self.store.create_delegation(self.task)
        divergent = make_envelope(objective="Different objective.")
        self.assertEqual(divergent.delegation_id, self.task.delegation_id)
        with self.assertRaises(DelegationConflictError):
            self.store.create_delegation(divergent)

    def test_missing_delegation_is_typed(self):
        with self.assertRaises(DelegationNotFoundError):
            self.store.get_delegation("delegation-missing")

    def test_reopen_recovers_delegation(self):
        self.store.create_delegation(self.task)
        reopened = SQLiteDelegationStore(self.db)
        self.assertEqual(reopened.get_delegation(self.task.delegation_id), self.task)

    def test_delegation_payload_tampering_is_detected(self):
        self.store.create_delegation(self.task)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute(
                "UPDATE delegations SET canonical_payload='{}' WHERE delegation_id=?",
                (self.task.delegation_id,),
            )
            connection.commit()
        with self.assertRaises(DelegationIntegrityError):
            self.store.get_delegation(self.task.delegation_id)

    def test_delegation_physical_linkage_tampering_is_detected(self):
        self.store.create_delegation(self.task)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute(
                "UPDATE delegations SET requested_target_agent_id='other' WHERE delegation_id=?",
                (self.task.delegation_id,),
            )
            connection.commit()
        with self.assertRaises(DelegationIntegrityError):
            self.store.get_delegation(self.task.delegation_id)

    def test_issue_read_and_replay_lease(self):
        self.store.create_delegation(self.task)
        artifact = make_lease(self.task)
        self.assertEqual(self.store.issue_lease(artifact), artifact)
        self.assertEqual(self.store.issue_lease(artifact), artifact)
        self.assertEqual(self.store.get_lease(artifact.lease_id), artifact)
        with closing(sqlite3.connect(self.db)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM capability_leases").fetchone()[0]
        self.assertEqual(count, 1)

    def test_lease_requires_existing_active_delegation(self):
        artifact = make_lease(self.task)
        with self.assertRaises(DelegationNotFoundError):
            self.store.issue_lease(artifact)
        self.store.create_delegation(self.task)
        self.store.cancel_delegation(
            self.task.delegation_id,
            reason="cancel before delivery",
            cancelled_at="2026-08-27T12:01:00Z",
        )
        with self.assertRaises(InvalidDelegationStateTransitionError):
            self.store.issue_lease(artifact)

    def test_lease_must_be_bounded_by_envelope(self):
        self.store.create_delegation(self.task)
        cases = (
            {"recipient_agent_id": "wrong-agent"},
            {"allowed_operation": "other-operation"},
            {"allowed_tools": ["read_file", "shell"], "prohibited_tools": []},
            {"permitted_write_paths": ["outside/result.txt"]},
            {"max_runtime_seconds": 301},
            {"expected_result_schema_id": "schema://other/v1"},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(CapabilityViolationError):
                self.store.issue_lease(make_lease(self.task, **changes))

    def test_attempt_route_pair_has_one_lease_identity(self):
        self.store.create_delegation(self.task)
        first = make_lease(self.task)
        self.store.issue_lease(first)
        divergent = make_lease(self.task, max_runtime_seconds=60)
        self.assertNotEqual(first.lease_id, divergent.lease_id)
        with self.assertRaises(LeaseConflictError):
            self.store.issue_lease(divergent)

    def test_reopen_recovers_lease_and_uniqueness(self):
        self.store.create_delegation(self.task)
        artifact = make_lease(self.task)
        self.store.issue_lease(artifact)
        reopened = SQLiteDelegationStore(self.db)
        self.assertEqual(reopened.get_lease(artifact.lease_id), artifact)
        self.assertEqual(reopened.issue_lease(artifact), artifact)

    def test_lease_payload_and_physical_tampering_detected(self):
        self.store.create_delegation(self.task)
        artifact = make_lease(self.task)
        self.store.issue_lease(artifact)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute(
                "UPDATE capability_leases SET recipient_agent_id='wrong' WHERE lease_id=?",
                (artifact.lease_id,),
            )
            connection.commit()
        with self.assertRaises(DelegationIntegrityError):
            self.store.get_lease(artifact.lease_id)

    def test_cancel_before_delivery_is_durable_and_idempotent(self):
        self.store.create_delegation(self.task)
        kwargs = dict(reason="cancel before delivery", cancelled_at="2026-08-27T12:01:00Z")
        self.store.cancel_delegation(self.task.delegation_id, **kwargs)
        self.store.cancel_delegation(self.task.delegation_id, **kwargs)
        self.assertEqual(self.store.delegation_status(self.task.delegation_id), "CANCELLED")
        reopened = SQLiteDelegationStore(self.db)
        self.assertEqual(reopened.delegation_status(self.task.delegation_id), "CANCELLED")

    def test_conflicting_cancellation_replay_fails_closed(self):
        self.store.create_delegation(self.task)
        self.store.cancel_delegation(
            self.task.delegation_id,
            reason="first",
            cancelled_at="2026-08-27T12:01:00Z",
        )
        with self.assertRaises(CancellationConflictError):
            self.store.cancel_delegation(
                self.task.delegation_id,
                reason="different",
                cancelled_at="2026-08-27T12:01:00Z",
            )

    def test_revocation_is_durable_and_idempotent(self):
        self.store.create_delegation(self.task)
        artifact = make_lease(self.task)
        self.store.issue_lease(artifact)
        kwargs = dict(reason="revoked before acceptance", revoked_at="2026-08-27T12:02:00Z")
        self.store.revoke_lease(artifact.lease_id, **kwargs)
        self.store.revoke_lease(artifact.lease_id, **kwargs)
        reopened = SQLiteDelegationStore(self.db)
        self.assertEqual(reopened.lease_status(artifact.lease_id), "REVOKED")
        with self.assertRaises(LeaseRevokedError):
            reopened.validate_lease_use(
                artifact.lease_id,
                recipient_agent_id=artifact.recipient_agent_id,
                delegation_id=artifact.delegation_id,
                operation=artifact.allowed_operation,
                at="2026-08-27T12:05:00Z",
            )

    def test_conflicting_revocation_replay_fails_closed(self):
        self.store.create_delegation(self.task)
        artifact = make_lease(self.task)
        self.store.issue_lease(artifact)
        self.store.revoke_lease(
            artifact.lease_id, reason="first", revoked_at="2026-08-27T12:02:00Z"
        )
        with self.assertRaises(CancellationConflictError):
            self.store.revoke_lease(
                artifact.lease_id, reason="different", revoked_at="2026-08-27T12:02:00Z"
            )

    def test_cancelled_delegation_never_becomes_deliverable(self):
        self.store.create_delegation(self.task)
        artifact = make_lease(self.task)
        self.store.issue_lease(artifact)
        self.store.cancel_delegation(
            self.task.delegation_id,
            reason="cancelled",
            cancelled_at="2026-08-27T12:01:00Z",
        )
        with self.assertRaises(InvalidDelegationStateTransitionError):
            self.store.validate_lease_use(
                artifact.lease_id,
                recipient_agent_id=artifact.recipient_agent_id,
                delegation_id=artifact.delegation_id,
                operation=artifact.allowed_operation,
                at="2026-08-27T12:05:00Z",
            )

    def test_expired_lease_never_becomes_deliverable(self):
        self.store.create_delegation(self.task)
        artifact = make_lease(self.task)
        self.store.issue_lease(artifact)
        for timestamp in (artifact.expires_at, "2026-08-27T12:20:00Z"):
            with self.subTest(timestamp=timestamp), self.assertRaises(LeaseExpiredError):
                self.store.validate_lease_use(
                    artifact.lease_id,
                    recipient_agent_id=artifact.recipient_agent_id,
                    delegation_id=artifact.delegation_id,
                    operation=artifact.allowed_operation,
                    at=timestamp,
                )

    def test_valid_lease_use_returns_durable_artifact(self):
        self.store.create_delegation(self.task)
        artifact = make_lease(self.task)
        self.store.issue_lease(artifact)
        validated = self.store.validate_lease_use(
            artifact.lease_id,
            recipient_agent_id=artifact.recipient_agent_id,
            delegation_id=artifact.delegation_id,
            operation=artifact.allowed_operation,
            tools=["read_file"],
            read_paths=["inputs/source.txt"],
            write_paths=["outputs/report.json"],
            at="2026-08-27T12:05:00Z",
        )
        self.assertEqual(validated, artifact)

    def test_integrity_report_counts_all_durable_records(self):
        self.store.create_delegation(self.task)
        artifact = make_lease(self.task)
        self.store.issue_lease(artifact)
        self.store.revoke_lease(
            artifact.lease_id, reason="revoked", revoked_at="2026-08-27T12:02:00Z"
        )
        self.store.cancel_delegation(
            self.task.delegation_id, reason="cancelled", cancelled_at="2026-08-27T12:03:00Z"
        )
        self.assertEqual(
            self.store.verify_integrity(),
            {
                "delegations": 1,
                "leases": 1,
                "cancellations": 1,
                "revocations": 1,
                "mailbox_messages": 0,
                "delivery_events": 0,
                "receipts": 0,
            },
        )

    def test_mutated_artifact_is_rejected_before_write(self):
        with self.assertRaises(DelegationIntegrityError):
            self.store.create_delegation(replace(self.task, objective="mutated"))


if __name__ == "__main__":
    unittest.main()
