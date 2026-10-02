from __future__ import annotations

import unittest
from dataclasses import replace

from tools.hermes_core.delegated_task import (
    DelegationIntegrityError,
    InvalidCanonicalEnvelopeError,
)
from tools.hermes_core.delegation_delivery import (
    REJECTION_REASON_CODES,
    ReceiverMismatchError,
    build_delegation_receipt,
    build_delivery_event,
    build_mailbox_message,
    reconstruct_delegation_receipt,
    reconstruct_delivery_event,
    reconstruct_mailbox_message,
)


H = "a" * 64


def make_message(**overrides):
    values = {
        "mailbox_id": "codex-cli-agent",
        "mailbox_sequence": 1,
        "message_type": "DELEGATION",
        "sender_agent_id": "hermes-agent-router",
        "recipient_agent_id": "codex-cli-agent",
        "delegation_id": "delegation-1",
        "attempt_id": "attempt-1",
        "idempotency_key": "delivery-1",
        "payload_schema_id": "hermes.delegation_delivery/v1",
        "payload_hash": H,
        "created_at": "2026-08-28T12:00:00Z",
    }
    values.update(overrides)
    return build_mailbox_message(**values)


def make_receipt(**overrides):
    values = {
        "delegation_id": "delegation-1",
        "delegated_task_hash": "a" * 64,
        "capability_lease_id": "lease-1",
        "capability_lease_hash": "b" * 64,
        "authorization_id": "authorization-1",
        "authorization_hash": "c" * 64,
        "attempt_id": "attempt-1",
        "attempt_hash": "d" * 64,
        "route_id": "route-1",
        "route_hash": "e" * 64,
        "launch_attempt_id": "launch-1",
        "launch_attempt_hash": "f" * 64,
        "receiver_agent_id": "codex-cli-agent",
        "receiver_descriptor_hash": "1" * 64,
        "receiver_implementation": "deterministic-test-receiver",
        "receiver_version": "1.0",
        "runtime_run_id": "runtime-1",
        "outcome": "ACCEPTED",
        "reason_code": None,
        "reason_summary": None,
        "received_at": "2026-08-28T12:00:01Z",
        "decided_at": "2026-08-28T12:00:02Z",
    }
    values.update(overrides)
    return build_delegation_receipt(**values)


class MailboxMessageContractTests(unittest.TestCase):
    def test_identity_depends_only_on_mailbox_and_idempotency_key(self):
        first = make_message(payload_hash="a" * 64)
        divergent = make_message(payload_hash="b" * 64)
        self.assertEqual(first.message_id, divergent.message_id)
        self.assertNotEqual(first.artifact_hash, divergent.artifact_hash)

    def test_round_trip_and_hash_verification(self):
        message = make_message()
        self.assertEqual(reconstruct_mailbox_message(message.to_canonical_dict()), message)
        message.verify_hash()

    def test_mailbox_must_equal_recipient(self):
        with self.assertRaises(ReceiverMismatchError):
            make_message(mailbox_id="other-agent")

    def test_unknown_message_type_is_rejected(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            make_message(message_type="RUN_NOW")

    def test_tampered_message_is_rejected(self):
        with self.assertRaises(DelegationIntegrityError):
            replace(make_message(), payload_hash="b" * 64).verify_hash()


class DeliveryEventContractTests(unittest.TestCase):
    def test_claim_event_round_trip(self):
        event = build_delivery_event(
            message_id="mailmsg-1", message_hash="a" * 64,
            mailbox_id="codex-cli-agent", event_sequence=1,
            previous_event_hash=None, state="CLAIMED",
            actor_agent_id="codex-cli-agent", claim_token="claim-1",
            claim_expires_at="2026-08-28T12:05:00Z",
            occurred_at="2026-08-28T12:00:00Z",
        )
        self.assertEqual(reconstruct_delivery_event(event.to_canonical_dict()), event)
        event.verify_hash()

    def test_claim_requires_token_and_expiry(self):
        for token, expiry in ((None, "2026-08-28T12:05:00Z"), ("claim-1", None)):
            with self.subTest(token=token, expiry=expiry), self.assertRaises(InvalidCanonicalEnvelopeError):
                build_delivery_event(
                    message_id="mailmsg-1", message_hash="a" * 64,
                    mailbox_id="codex-cli-agent", event_sequence=1,
                    previous_event_hash=None, state="CLAIMED",
                    actor_agent_id="codex-cli-agent", claim_token=token,
                    claim_expires_at=expiry, occurred_at="2026-08-28T12:00:00Z",
                )

    def test_event_hash_chain_material_changes_identity(self):
        base = dict(
            message_id="mailmsg-1", message_hash="a" * 64,
            mailbox_id="codex-cli-agent", event_sequence=2,
            state="ACKNOWLEDGED", actor_agent_id="codex-cli-agent",
            claim_token="claim-1", claim_expires_at="2026-08-28T12:05:00Z",
            occurred_at="2026-08-28T12:01:00Z",
        )
        first = build_delivery_event(previous_event_hash="b" * 64, **base)
        second = build_delivery_event(previous_event_hash="c" * 64, **base)
        self.assertNotEqual(first.event_id, second.event_id)


class DelegationReceiptContractTests(unittest.TestCase):
    def test_accepted_receipt_round_trip(self):
        receipt = make_receipt()
        self.assertEqual(reconstruct_delegation_receipt(receipt.to_canonical_dict()), receipt)
        receipt.verify_hash()

    def test_rejected_receipt_uses_frozen_reason_taxonomy(self):
        for reason in REJECTION_REASON_CODES:
            with self.subTest(reason=reason):
                receipt = make_receipt(
                    outcome="REJECTED", reason_code=reason,
                    reason_summary="Bounded receiver rejection.",
                )
                self.assertEqual(receipt.outcome, "REJECTED")

    def test_rejected_receipt_requires_reason(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            make_receipt(outcome="REJECTED")

    def test_accepted_receipt_forbids_rejection_material(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            make_receipt(reason_code="WRONG_RECEIVER", reason_summary="wrong")

    def test_decision_cannot_precede_receipt(self):
        with self.assertRaises(InvalidCanonicalEnvelopeError):
            make_receipt(decided_at="2026-08-28T12:00:00Z")

    def test_receipt_identity_is_separate_from_other_lineage_ids(self):
        receipt = make_receipt()
        lineage = {
            receipt.delegation_id, receipt.capability_lease_id,
            receipt.authorization_id, receipt.attempt_id,
            receipt.route_id, receipt.launch_attempt_id,
            receipt.runtime_run_id,
        }
        self.assertNotIn(receipt.receipt_id, lineage)


if __name__ == "__main__":
    unittest.main()
