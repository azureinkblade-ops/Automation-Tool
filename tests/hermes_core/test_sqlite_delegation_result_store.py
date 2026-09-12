from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from tools.hermes_core.delegated_task import (
    DelegationIntegrityError,
    DelegationNotFoundError,
    InvalidCanonicalEnvelopeError,
)
from tools.hermes_core.delegation_result import (
    DelegationResultConflictError,
    build_delegation_result,
    reconstruct_delegation_result,
    reconstruct_result_delivery,
)
from tools.hermes_core.sqlite_delegation_result_store import (
    DelegationResultStoreError,
    SQLiteDelegationResultStore,
)
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tests.hermes_core.test_sqlite_delegation_delivery import make_receipt
from tests.hermes_core.test_sqlite_delegation_store import make_envelope, make_lease


def make_result(task, lease, receipt, **overrides):
    values = {
        "delegation_id": task.delegation_id,
        "delegated_task_hash": task.artifact_hash,
        "authorization_id": lease.authorization_id,
        "authorization_hash": lease.authorization_hash,
        "attempt_id": lease.attempt_id,
        "attempt_hash": lease.attempt_hash,
        "launch_attempt_id": receipt.launch_attempt_id,
        "launch_attempt_hash": receipt.launch_attempt_hash,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.artifact_hash,
        "receiver_agent_id": receipt.receiver_agent_id,
        "receiver_descriptor_hash": receipt.receiver_descriptor_hash,
        "runtime_run_id": receipt.runtime_run_id,
        "outcome": "SUCCEEDED",
        "result_payload": {"summary": "Bounded delegated task completed."},
        "output_manifest": [{
            "ordinal": 0,
            "reference_type": "workspace_file",
            "reference": "outputs/report.json",
            "sha256": "1" * 64,
            "media_type": "application/json",
        }],
        "evidence_manifest": [{
            "ordinal": 0,
            "evidence_type": "output_sha256",
            "sha256": "1" * 64,
        }],
        "started_at": "2026-08-27T12:05:03Z",
        "completed_at": "2026-08-27T12:05:04Z",
        "error_code": None,
        "error_summary": None,
    }
    values.update(overrides)
    return build_delegation_result(**values)


class DelegationResultContractTests(unittest.TestCase):
    def setUp(self):
        self.task = make_envelope()
        self.lease = make_lease(self.task)
        self.receipt = make_receipt(self.task, self.lease)

    def test_result_and_delivery_round_trip(self):
        result = make_result(self.task, self.lease, self.receipt)
        result.verify_hash()
        self.assertEqual(reconstruct_delegation_result(result.to_canonical_dict()), result)

    def test_result_payload_must_be_an_object(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            make_result(self.task, self.lease, self.receipt, result_payload=["not", "an", "object"])

    def test_failed_result_requires_error_and_success_forbids_it(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            make_result(self.task, self.lease, self.receipt, outcome="FAILED")
        failed = make_result(
            self.task, self.lease, self.receipt, outcome="FAILED",
            error_code="BOUNDED_FAILURE", error_summary="Receiver reported failure.",
        )
        self.assertEqual(failed.outcome, "FAILED")
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            make_result(
                self.task, self.lease, self.receipt,
                error_code="NOT_ALLOWED", error_summary="not allowed",
            )

    def test_completion_cannot_precede_start(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            make_result(
                self.task, self.lease, self.receipt,
                completed_at="2026-08-27T12:05:02Z",
            )

    def test_result_identity_is_separate_from_frozen_lineage(self):
        result = make_result(self.task, self.lease, self.receipt)
        lineage = {
            result.delegation_id, result.authorization_id, result.attempt_id,
            result.launch_attempt_id, result.receipt_id, result.runtime_run_id,
        }
        self.assertNotIn(result.result_id, lineage)


class SQLiteDelegationResultStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "delegations.db"
        self.authority = SQLiteDelegationStore(self.db)
        self.task = make_envelope()
        self.lease = make_lease(self.task)
        self.authority.create_delegation(self.task)
        self.authority.issue_lease(self.lease)
        message = self.authority.deliver_delegation(
            self.lease.lease_id,
            sender_agent_id="hermes-agent-router",
            delivered_at="2026-08-27T12:05:00Z",
        )
        self.authority.claim_message(
            message.message_id,
            recipient_agent_id=self.lease.recipient_agent_id,
            claim_token="receiver-claim",
            claimed_at="2026-08-27T12:05:00Z",
            claim_expires_at="2026-08-27T12:06:00Z",
        )
        self.receipt = make_receipt(self.task, self.lease)
        self.authority.record_receipt(self.receipt, source_message_id=message.message_id)
        self.result = make_result(self.task, self.lease, self.receipt)
        self.store = SQLiteDelegationResultStore(self.db)

    def record(self, result=None, **overrides):
        values = {
            "validated_result_schema_id": self.task.expected_result_schema_id,
            "delivered_at": "2026-08-27T12:05:05Z",
        }
        values.update(overrides)
        return self.store.record_verified_result_and_delivery(result or self.result, **values)

    def tearDown(self):
        self.temp.cleanup()

    def test_requires_existing_authority_database(self):
        missing = Path(self.temp.name) / "missing.db"
        with self.assertRaises(DelegationResultStoreError):
            SQLiteDelegationResultStore(missing)

    def test_uses_same_database_and_schema_version(self):
        with closing(sqlite3.connect(self.db)) as connection:
            version = connection.execute(
                "SELECT version FROM delegation_result_schema_version WHERE singleton=1"
            ).fetchone()[0]
            authority_version = connection.execute(
                "SELECT version FROM delegation_schema_version WHERE singleton=1"
            ).fetchone()[0]
        self.assertEqual((authority_version, version), (2, 1))

    def test_result_delivery_and_mailbox_message_are_atomic(self):
        durable, delivery, message_id = self.record()
        self.assertEqual(durable, self.result)
        self.assertEqual(self.store.get_result(self.lease.attempt_id), self.result)
        self.assertEqual(self.store.get_delivery(delivery.result_delivery_id), delivery)
        message = self.authority.get_message(message_id)
        self.assertEqual(message.message_type, "RESULT_DELIVERY")
        self.assertEqual(message.recipient_agent_id, self.task.originator_agent_id)
        body = self.authority.message_body(message_id)
        self.assertEqual(body["result"], self.result.to_canonical_dict())
        self.assertEqual(
            reconstruct_result_delivery(body["result_delivery"]), delivery
        )
        self.assertEqual(
            self.store.delegation_projection(self.task.delegation_id), "COMPLETED"
        )

    def test_exact_replay_and_restart_return_durable_truth(self):
        first = self.record()
        reopened = SQLiteDelegationResultStore(self.db)
        second = reopened.record_verified_result_and_delivery(
            self.result,
            validated_result_schema_id=self.task.expected_result_schema_id,
            delivered_at="2026-08-27T12:05:05Z",
        )
        self.assertEqual(first, second)
        self.assertEqual(
            len(self.authority.list_mailbox(self.task.originator_agent_id)), 1
        )

    def test_divergent_result_for_same_attempt_conflicts(self):
        self.record()
        divergent = make_result(
            self.task, self.lease, self.receipt,
            result_payload={"summary": "Different terminal result."},
        )
        with self.assertRaises(DelegationResultConflictError):
            self.record(divergent)

    def test_result_requires_accepted_exact_receipt_lineage(self):
        cases = (
            {"authorization_hash": "9" * 64},
            {"launch_attempt_hash": "8" * 64},
            {"receiver_descriptor_hash": "7" * 64},
            {"runtime_run_id": "different-runtime"},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(DelegationIntegrityError):
                self.record(make_result(self.task, self.lease, self.receipt, **changes))

    def test_schema_evidence_and_output_scope_fail_closed(self):
        with self.assertRaises(DelegationIntegrityError):
            self.record(validated_result_schema_id="schema://other/v1")
        with self.assertRaises(DelegationIntegrityError):
            self.record(make_result(
                self.task, self.lease, self.receipt, evidence_manifest=[{
                    "ordinal": 0, "evidence_type": "different", "sha256": "1" * 64,
                }],
            ))
        with self.assertRaises(DelegationIntegrityError):
            self.record(make_result(
                self.task, self.lease, self.receipt, output_manifest=[{
                    "ordinal": 0, "reference_type": "workspace_file",
                    "reference": "outside/report.json", "sha256": "1" * 64,
                    "media_type": "application/json",
                }],
            ))

    def test_partial_transaction_rolls_back(self):
        with patch(
            "tools.hermes_core.sqlite_delegation_result_store.build_result_delivery",
            side_effect=RuntimeError("simulated crash"),
        ):
            with self.assertRaises(RuntimeError):
                self.record()
        with self.assertRaises(DelegationNotFoundError):
            self.store.get_result(self.lease.attempt_id)

    def test_originator_restart_claims_and_acknowledges_same_result(self):
        _, delivery, message_id = self.record()
        restarted_originator = SQLiteDelegationStore(self.db)
        message = restarted_originator.get_message(message_id)
        self.assertEqual(message.idempotency_key, delivery.result_delivery_id)
        restarted_originator.claim_message(
            message_id,
            recipient_agent_id=self.task.originator_agent_id,
            claim_token="originator-result-claim",
            claimed_at="2026-08-27T12:05:06Z",
            claim_expires_at="2026-08-27T12:06:00Z",
        )
        restarted_originator.acknowledge_message(
            message_id,
            recipient_agent_id=self.task.originator_agent_id,
            claim_token="originator-result-claim",
            acknowledged_at="2026-08-27T12:05:07Z",
        )
        self.assertEqual(restarted_originator.delivery_state(message_id), "ACKNOWLEDGED")

    def test_result_and_delivery_tampering_is_detected(self):
        _, delivery, _ = self.record()
        for table, key, value, loader in (
            ("delegation_results", "attempt_id", self.lease.attempt_id, lambda store: store.get_result(self.lease.attempt_id)),
            ("result_deliveries", "result_delivery_id", delivery.result_delivery_id, lambda store: store.get_delivery(delivery.result_delivery_id)),
        ):
            with self.subTest(table=table), tempfile.TemporaryDirectory() as directory:
                copy = Path(directory) / "tamper.db"
                copy.write_bytes(self.db.read_bytes())
                with closing(sqlite3.connect(copy)) as connection:
                    connection.execute(
                        f"UPDATE {table} SET canonical_payload='{{}}' WHERE {key}=?",
                        (value,),
                    )
                    connection.commit()
                with self.assertRaises(DelegationIntegrityError):
                    loader(SQLiteDelegationResultStore(copy))

    def test_unknown_result_schema_version_fails_closed(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute(
                "UPDATE delegation_result_schema_version SET version=99"
            )
            connection.commit()
        with self.assertRaises(DelegationResultStoreError):
            SQLiteDelegationResultStore(self.db)


if __name__ == "__main__":
    unittest.main()
