from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tools.hermes_core.delegated_task import (
    DelegationIntegrityError,
    InvalidDelegationStateTransitionError,
    LeaseExpiredError,
    LeaseRevokedError,
)
from tools.hermes_core.delegation_delivery import (
    InvalidAcceptanceTransitionError,
    InvalidMessageStateError,
    MailboxDeliveryConflictError,
    ReceiverAcceptanceConflictError,
    ReceiverMismatchError,
    build_delegation_receipt,
)
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tests.hermes_core.test_sqlite_delegation_store import make_envelope, make_lease


def make_receipt(task, lease, **overrides):
    values = {
        "delegation_id": task.delegation_id,
        "delegated_task_hash": task.artifact_hash,
        "capability_lease_id": lease.lease_id,
        "capability_lease_hash": lease.artifact_hash,
        "authorization_id": lease.authorization_id,
        "authorization_hash": lease.authorization_hash,
        "attempt_id": lease.attempt_id,
        "attempt_hash": lease.attempt_hash,
        "route_id": lease.route_id,
        "route_hash": lease.route_hash,
        "launch_attempt_id": "launch-1",
        "launch_attempt_hash": "f" * 64,
        "receiver_agent_id": lease.recipient_agent_id,
        "receiver_descriptor_hash": lease.worker_descriptor_hash,
        "receiver_implementation": "deterministic-test-receiver",
        "receiver_version": "1.0",
        "runtime_run_id": "runtime-1",
        "outcome": "ACCEPTED",
        "reason_code": None,
        "reason_summary": None,
        "received_at": "2026-08-27T12:05:01Z",
        "decided_at": "2026-08-27T12:05:02Z",
    }
    values.update(overrides)
    return build_delegation_receipt(**values)


class SQLiteDelegationDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "delegations.db"
        self.store = SQLiteDelegationStore(self.db)
        self.task = make_envelope()
        self.lease = make_lease(self.task)
        self.store.create_delegation(self.task)
        self.store.issue_lease(self.lease)

    def tearDown(self):
        self.temp.cleanup()

    def deliver(self, **overrides):
        values = {
            "sender_agent_id": "hermes-agent-router",
            "delivered_at": "2026-08-27T12:05:00Z",
        }
        values.update(overrides)
        return self.store.deliver_delegation(self.lease.lease_id, **values)

    def claim(self, message, **overrides):
        values = {
            "recipient_agent_id": self.lease.recipient_agent_id,
            "claim_token": "claim-1",
            "claimed_at": "2026-08-27T12:05:00Z",
            "claim_expires_at": "2026-08-27T12:06:00Z",
        }
        values.update(overrides)
        return self.store.claim_message(message.message_id, **values)

    def test_delivery_is_durable_and_contains_exact_task_and_lease(self):
        message = self.deliver()
        self.assertEqual(self.store.get_message(message.message_id), message)
        body = self.store.message_body(message.message_id)
        self.assertEqual(body["delegated_task"]["artifact_hash"], self.task.artifact_hash)
        self.assertEqual(body["capability_lease"]["artifact_hash"], self.lease.artifact_hash)
        self.assertEqual(self.store.delivery_state(message.message_id), "PENDING")

    def test_same_delivery_replay_returns_same_truth(self):
        first = self.deliver()
        second = self.deliver()
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.list_mailbox(self.lease.recipient_agent_id)), 1)

    def test_divergent_delivery_replay_conflicts(self):
        self.deliver(idempotency_key="same-key")
        with self.assertRaises(MailboxDeliveryConflictError):
            self.deliver(idempotency_key="same-key", delivered_at="2026-08-27T12:05:01Z")

    def test_lost_delivery_response_recovers_without_duplicate(self):
        persisted = self.deliver()
        reopened = SQLiteDelegationStore(self.db)
        replayed = reopened.deliver_delegation(
            self.lease.lease_id,
            sender_agent_id="hermes-agent-router",
            delivered_at="2026-08-27T12:05:00Z",
        )
        self.assertEqual(replayed, persisted)

    def test_crash_during_delivery_transaction_rolls_back(self):
        original = self.store._insert_message

        def insert_then_fail(connection, **kwargs):
            original(connection, **kwargs)
            raise RuntimeError("simulated crash")

        with patch.object(self.store, "_insert_message", side_effect=insert_then_fail):
            with self.assertRaises(RuntimeError):
                self.deliver()
        self.assertEqual(self.store.list_mailbox(self.lease.recipient_agent_id), [])

    def test_cancel_revoke_and_expiry_block_new_delivery(self):
        cases = ("cancel", "revoke", "expire")
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as directory:
                    store = SQLiteDelegationStore(Path(directory) / "case.db")
                    task = make_envelope()
                    lease = make_lease(task)
                    store.create_delegation(task)
                    store.issue_lease(lease)
                    if case == "cancel":
                        store.cancel_delegation(task.delegation_id, reason="stop", cancelled_at="2026-08-27T12:04:00Z")
                        error = InvalidDelegationStateTransitionError
                        at = "2026-08-27T12:05:00Z"
                    elif case == "revoke":
                        store.revoke_lease(lease.lease_id, reason="stop", revoked_at="2026-08-27T12:04:00Z")
                        error = LeaseRevokedError
                        at = "2026-08-27T12:05:00Z"
                    else:
                        error = LeaseExpiredError
                        at = lease.expires_at
                    with self.assertRaises(error):
                        store.deliver_delegation(lease.lease_id, sender_agent_id="router", delivered_at=at)

    def test_mailbox_sequence_is_committed_order(self):
        first = self.deliver()
        task2 = make_envelope(originator_request_id="request-2", task_id="task-2")
        lease2 = make_lease(task2, authorization_id="authorization-2", attempt_id="attempt-2", route_id="route-2")
        self.store.create_delegation(task2)
        self.store.issue_lease(lease2)
        second = self.store.deliver_delegation(
            lease2.lease_id, sender_agent_id="router", delivered_at="2026-08-27T12:05:01Z"
        )
        self.assertEqual((first.mailbox_sequence, second.mailbox_sequence), (1, 2))

    def test_claim_is_durable_idempotent_and_receiver_bound(self):
        message = self.deliver()
        first = self.claim(message)
        replay = self.claim(message)
        self.assertEqual(first, replay)
        self.assertEqual(self.store.delivery_state(message.message_id), "CLAIMED")
        with self.assertRaises(ReceiverMismatchError):
            self.store.claim_message(
                message.message_id, recipient_agent_id="other-agent",
                claim_token="claim-2", claimed_at="2026-08-27T12:05:01Z",
                claim_expires_at="2026-08-27T12:06:01Z",
            )

    def test_active_claim_blocks_other_claim_but_expiry_redelivers_same_message(self):
        message = self.deliver()
        first = self.claim(message)
        with self.assertRaises(InvalidMessageStateError):
            self.claim(message, claim_token="claim-2", claimed_at="2026-08-27T12:05:30Z")
        second = self.claim(
            message, claim_token="claim-2", claimed_at="2026-08-27T12:06:00Z",
            claim_expires_at="2026-08-27T12:07:00Z",
        )
        self.assertEqual(second.message_id, first.message_id)
        self.assertEqual(second.event_sequence, 2)

    def test_same_claim_token_with_changed_material_conflicts(self):
        message = self.deliver()
        self.claim(message)
        with self.assertRaises(InvalidMessageStateError):
            self.claim(
                message, claimed_at="2026-08-27T12:05:01Z",
                claim_expires_at="2026-08-27T12:06:01Z",
            )

    def test_acknowledgement_requires_live_matching_claim_and_replays(self):
        message = self.deliver()
        self.claim(message)
        acknowledged = self.store.acknowledge_message(
            message.message_id, recipient_agent_id=self.lease.recipient_agent_id,
            claim_token="claim-1", acknowledged_at="2026-08-27T12:05:30Z",
        )
        replay = self.store.acknowledge_message(
            message.message_id, recipient_agent_id=self.lease.recipient_agent_id,
            claim_token="claim-1", acknowledged_at="2026-08-27T12:05:30Z",
        )
        self.assertEqual(acknowledged, replay)
        self.assertEqual(self.store.delivery_state(message.message_id), "ACKNOWLEDGED")
        with self.assertRaises(InvalidMessageStateError):
            self.claim(message, claim_token="claim-3", claimed_at="2026-08-27T12:07:00Z")

    def test_same_ack_token_with_changed_material_conflicts(self):
        message = self.deliver()
        self.claim(message)
        self.store.acknowledge_message(
            message.message_id, recipient_agent_id=self.lease.recipient_agent_id,
            claim_token="claim-1", acknowledged_at="2026-08-27T12:05:30Z",
        )
        with self.assertRaises(InvalidMessageStateError):
            self.store.acknowledge_message(
                message.message_id, recipient_agent_id=self.lease.recipient_agent_id,
                claim_token="claim-1", acknowledged_at="2026-08-27T12:05:31Z",
            )

    def test_acceptance_and_receipt_message_are_atomic(self):
        message = self.deliver()
        self.claim(message)
        receipt = make_receipt(self.task, self.lease)
        self.assertEqual(self.store.record_receipt(receipt, source_message_id=message.message_id), receipt)
        self.assertEqual(self.store.get_receipt(self.lease.attempt_id), receipt)
        receipt_mailbox = self.store.list_mailbox("hermes-execution-authority")
        self.assertEqual(len(receipt_mailbox), 1)
        self.assertEqual(receipt_mailbox[0].message_type, "RECEIPT")

    def test_acceptance_replay_is_idempotent_and_divergence_conflicts(self):
        message = self.deliver()
        self.claim(message)
        receipt = make_receipt(self.task, self.lease)
        self.store.record_receipt(receipt, source_message_id=message.message_id)
        self.assertEqual(self.store.record_receipt(receipt, source_message_id=message.message_id), receipt)
        divergent = make_receipt(self.task, self.lease, receiver_version="2.0")
        with self.assertRaises(ReceiverAcceptanceConflictError):
            self.store.record_receipt(divergent, source_message_id=message.message_id)

    def test_rejection_is_durable_and_cannot_become_acceptance(self):
        message = self.deliver()
        self.claim(message)
        rejected = make_receipt(
            self.task, self.lease, outcome="REJECTED",
            reason_code="UNSUPPORTED_OPERATION", reason_summary="unsupported",
        )
        self.store.record_receipt(rejected, source_message_id=message.message_id)
        accepted = make_receipt(self.task, self.lease)
        with self.assertRaises(ReceiverAcceptanceConflictError):
            self.store.record_receipt(accepted, source_message_id=message.message_id)

    def test_wrong_receiver_task_lease_or_attempt_fails_closed(self):
        message = self.deliver()
        self.claim(message)
        changes = (
            {"receiver_agent_id": "other-agent"},
            {"delegated_task_hash": "9" * 64},
            {"capability_lease_hash": "8" * 64},
            {"attempt_hash": "7" * 64},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(InvalidAcceptanceTransitionError):
                self.store.record_receipt(
                    make_receipt(self.task, self.lease, **change),
                    source_message_id=message.message_id,
                )

    def test_acceptance_requires_a_live_receiver_claim(self):
        message = self.deliver()
        receipt = make_receipt(self.task, self.lease)
        with self.assertRaises(InvalidAcceptanceTransitionError):
            self.store.record_receipt(receipt, source_message_id=message.message_id)
        self.claim(message, claim_expires_at="2026-08-27T12:05:02Z")
        with self.assertRaises(InvalidAcceptanceTransitionError):
            self.store.record_receipt(receipt, source_message_id=message.message_id)

    def test_cancellation_and_revocation_after_delivery_block_acceptance(self):
        for kind in ("cancel", "revoke"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                store = SQLiteDelegationStore(Path(directory) / "race.db")
                task = make_envelope()
                lease = make_lease(task)
                store.create_delegation(task)
                store.issue_lease(lease)
                message = store.deliver_delegation(lease.lease_id, sender_agent_id="router", delivered_at="2026-08-27T12:05:00Z")
                store.claim_message(
                    message.message_id, recipient_agent_id=lease.recipient_agent_id,
                    claim_token="claim", claimed_at="2026-08-27T12:05:00Z",
                    claim_expires_at="2026-08-27T12:06:00Z",
                )
                if kind == "cancel":
                    store.cancel_delegation(task.delegation_id, reason="stop", cancelled_at="2026-08-27T12:05:01Z")
                    error = InvalidAcceptanceTransitionError
                else:
                    store.revoke_lease(lease.lease_id, reason="stop", revoked_at="2026-08-27T12:05:01Z")
                    error = LeaseRevokedError
                with self.assertRaises(error):
                    store.record_receipt(make_receipt(task, lease), source_message_id=message.message_id)

    def test_rejection_can_record_authoritative_preacceptance_cancellation(self):
        message = self.deliver()
        self.claim(message)
        self.store.cancel_delegation(
            self.task.delegation_id, reason="stop", cancelled_at="2026-08-27T12:05:01Z"
        )
        rejected = make_receipt(
            self.task, self.lease, outcome="REJECTED",
            reason_code="REVOKED_OR_CANCELLED", reason_summary="cancelled",
        )
        self.assertEqual(
            self.store.record_receipt(rejected, source_message_id=message.message_id), rejected
        )

    def test_later_cancellation_does_not_rewrite_historical_acceptance(self):
        message = self.deliver()
        self.claim(message)
        receipt = make_receipt(self.task, self.lease)
        self.store.record_receipt(receipt, source_message_id=message.message_id)
        self.store.cancel_delegation(
            self.task.delegation_id, reason="later", cancelled_at="2026-08-27T12:05:03Z"
        )
        self.assertEqual(self.store.get_receipt(self.lease.attempt_id), receipt)

    def test_reopen_recovers_delivery_claim_and_receipt(self):
        message = self.deliver()
        claim = self.claim(message)
        receipt = make_receipt(self.task, self.lease)
        self.store.record_receipt(receipt, source_message_id=message.message_id)
        reopened = SQLiteDelegationStore(self.db)
        self.assertEqual(reopened.get_message(message.message_id), message)
        self.assertEqual(reopened.delivery_state(message.message_id), claim.state)
        self.assertEqual(reopened.get_receipt(self.lease.attempt_id), receipt)

    def test_integrity_detects_message_event_and_receipt_tampering(self):
        message = self.deliver()
        self.claim(message)
        receipt = make_receipt(self.task, self.lease)
        self.store.record_receipt(receipt, source_message_id=message.message_id)
        tables = (
            ("agent_mailbox_messages", "message_id", message.message_id),
            ("agent_mailbox_delivery_events", "message_id", message.message_id),
            ("delegation_receipts", "attempt_id", self.lease.attempt_id),
        )
        for table, key, value in tables:
            with self.subTest(table=table), tempfile.TemporaryDirectory() as directory:
                copy = Path(directory) / "tamper.db"
                copy.write_bytes(self.db.read_bytes())
                with closing(sqlite3.connect(copy)) as connection:
                    connection.execute(
                        f"UPDATE {table} SET canonical_payload='{{}}' WHERE {key}=?", (value,)
                    )
                    connection.commit()
                with self.assertRaises(DelegationIntegrityError):
                    SQLiteDelegationStore(copy).verify_integrity()

    def test_v1_database_migrates_atomically_and_preserves_r12a_rows(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("DROP TABLE delegation_receipts")
            connection.execute("DROP TABLE agent_mailbox_delivery_events")
            connection.execute("DROP TABLE agent_mailbox_messages")
            connection.execute("UPDATE delegation_schema_version SET version=1")
            connection.commit()
        migrated = SQLiteDelegationStore(self.db)
        self.assertEqual(migrated.get_delegation(self.task.delegation_id), self.task)
        self.assertEqual(migrated.get_lease(self.lease.lease_id), self.lease)
        with closing(sqlite3.connect(self.db)) as connection:
            version = connection.execute("SELECT version FROM delegation_schema_version").fetchone()[0]
        self.assertEqual(version, 2)

    def test_partial_v1_migration_fails_closed_without_version_change(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE delegation_schema_version SET version=1")
            connection.commit()
        from tools.hermes_core.sqlite_delegation_store import DelegationStoreSchemaError
        with self.assertRaises(DelegationStoreSchemaError):
            SQLiteDelegationStore(self.db)
        with closing(sqlite3.connect(self.db)) as connection:
            version = connection.execute("SELECT version FROM delegation_schema_version").fetchone()[0]
        self.assertEqual(version, 1)


if __name__ == "__main__":
    unittest.main()
