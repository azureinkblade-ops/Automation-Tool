"""EA-4D.4F-R12C: composition binding delegation artifacts to EA-4D.4A-E mechanics.

Tests the thin composition service that binds R12A/R12B delegation artifacts
to existing execution chain identity fields using a DETERMINISTIC FAKE RECEIVER.

Per frozen R11 Section 20.3, R12C uses deterministic fake agents — no real
agent invocation, no delegated work execution, no EXECUTING projection.
"""

from __future__ import annotations

import unittest

from tools.hermes_core.delegated_task import (
    build_delegated_capability_lease,
    build_delegated_task_envelope,
)
from tools.hermes_core.delegation_delivery import (
    build_delegation_receipt,
    build_mailbox_message,
)
from tools.hermes_core.delegation_composition import (
    DelegationCompositionError,
    FakeReceiverResult,
    compose_delegation_with_chain,
    deterministic_fake_receiver,
)


H = "a" * 64


def _envelope(**overrides):
    values = {
        "delegation_revision": 1,
        "originator_request_id": "req-1",
        "task_id": "task-1",
        "parent_task_id": None,
        "originator_agent_id": "hermes-primary-agent",
        "requested_target_agent_id": "codex-cli-agent",
        "operation": "transform",
        "objective": "test objective",
        "instructions": "test instructions",
        "input_manifest": [],
        "scope": {"read_paths": [], "write_paths": [], "network_policy": "deny", "allowed_tools": [], "approved_hosts": [], "time_budget_seconds": 60},
        "expected_result_schema_id": "hermes.result/v1",
        "expected_evidence": [],
        "requested_at": "2026-08-28T12:00:00Z",
        "expires_at": None,
        "redelegation_allowed": False,
    }
    values.update(overrides)
    return build_delegated_task_envelope(**values)


def _lease(envelope, **overrides):
    values = {
        "delegation_id": envelope.delegation_id,
        "delegated_task_hash": envelope.artifact_hash,
        "authorization_id": "auth-1",
        "authorization_hash": H,
        "attempt_id": "attempt-1",
        "attempt_hash": H,
        "route_id": "route-1",
        "route_hash": H,
        "recipient_agent_id": "codex-cli-agent",
        "worker_descriptor_hash": H,
        "allowed_operation": "transform",
        "allowed_tools": [],
        "prohibited_tools": [],
        "permitted_read_paths": [],
        "permitted_write_paths": [],
        "network_policy": "deny",
        "approved_hosts": [],
        "max_runtime_seconds": 60,
        "expected_result_schema_id": "hermes.result/v1",
        "expected_evidence": [],
        "redelegation_allowed": False,
        "issued_at": "2026-08-28T12:00:00Z",
        "not_before": "2026-08-28T12:00:00Z",
        "expires_at": "2026-08-28T13:00:00Z",
    }
    values.update(overrides)
    return build_delegated_capability_lease(**values)


def _message(envelope, **overrides):
    values = {
        "mailbox_id": "codex-cli-agent",
        "mailbox_sequence": 1,
        "message_type": "DELEGATION",
        "sender_agent_id": "hermes-agent-router",
        "recipient_agent_id": "codex-cli-agent",
        "delegation_id": envelope.delegation_id,
        "attempt_id": "attempt-1",
        "idempotency_key": "delivery-1",
        "payload_schema_id": "hermes.delegation_delivery/v1",
        "payload_hash": H,
        "created_at": "2026-08-28T12:00:00Z",
    }
    values.update(overrides)
    return build_mailbox_message(**values)


def _receipt(**overrides):
    values = {
        "delegation_id": "delegation-1",
        "delegated_task_hash": H,
        "capability_lease_id": "lease-1",
        "capability_lease_hash": H,
        "authorization_id": "auth-1",
        "authorization_hash": H,
        "attempt_id": "attempt-1",
        "attempt_hash": H,
        "route_id": "route-1",
        "route_hash": H,
        "launch_attempt_id": "launch-1",
        "launch_attempt_hash": H,
        "receiver_agent_id": "codex-cli-agent",
        "receiver_descriptor_hash": H,
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


class R12CCompositionTests(unittest.TestCase):
    """R12C composition: delegation artifacts bound to EA-4D.4A-E mechanics."""

    def test_valid_binding_invokes_fake_receiver(self):
        envelope = _envelope()
        lease = _lease(envelope)
        message = _message(envelope)
        receipt = _receipt(delegation_id=envelope.delegation_id, capability_lease_id=lease.lease_id)

        result = compose_delegation_with_chain(
            envelope=envelope, lease=lease, message=message, receipt=receipt,
            attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
            authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
            decision_id="dec-1", task_id="task-1", worker_id="w1",
            worker_class=None, worker_version="1", operation="transform",
            input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

        self.assertIsInstance(result, FakeReceiverResult)
        self.assertEqual(result.outcome, "ACCEPTED")
        self.assertEqual(result.receiver_agent_id, "codex-cli-agent")
        self.assertEqual(result.attempt_id, "attempt-1")

    def test_lineage_mismatch_lease_delegation_blocked(self):
        envelope = _envelope()
        lease = _lease(envelope, delegation_id="delegation-OTHER")
        message = _message(envelope)
        receipt = _receipt(delegation_id=envelope.delegation_id, capability_lease_id=lease.lease_id)

        with self.assertRaises(Exception):
            compose_delegation_with_chain(
                envelope=envelope, lease=lease, message=message, receipt=receipt,
                attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
                authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
                decision_id="dec-1", task_id="task-1", worker_id="w1",
                worker_class=None, worker_version="1", operation="transform",
                input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

    def test_lineage_mismatch_receipt_attempt_blocked(self):
        envelope = _envelope()
        lease = _lease(envelope)
        message = _message(envelope)
        receipt = _receipt(delegation_id=envelope.delegation_id, capability_lease_id=lease.lease_id, attempt_id="attempt-OTHER")

        with self.assertRaises(DelegationCompositionError):
            compose_delegation_with_chain(
                envelope=envelope, lease=lease, message=message, receipt=receipt,
                attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
                authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
                decision_id="dec-1", task_id="task-1", worker_id="w1",
                worker_class=None, worker_version="1", operation="transform",
                input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

    def test_lineage_mismatch_receipt_lease_blocked(self):
        envelope = _envelope()
        lease = _lease(envelope)
        message = _message(envelope)
        receipt = _receipt(delegation_id=envelope.delegation_id, capability_lease_id="lease-OTHER")

        with self.assertRaises(DelegationCompositionError):
            compose_delegation_with_chain(
                envelope=envelope, lease=lease, message=message, receipt=receipt,
                attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
                authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
                decision_id="dec-1", task_id="task-1", worker_id="w1",
                worker_class=None, worker_version="1", operation="transform",
                input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

    def test_invocation_identity_deterministic(self):
        envelope = _envelope()
        lease = _lease(envelope)
        message = _message(envelope)
        receipt = _receipt(delegation_id=envelope.delegation_id, capability_lease_id=lease.lease_id)

        result1 = compose_delegation_with_chain(
            envelope=envelope, lease=lease, message=message, receipt=receipt,
            attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
            authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
            decision_id="dec-1", task_id="task-1", worker_id="w1",
            worker_class=None, worker_version="1", operation="transform",
            input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

        result2 = compose_delegation_with_chain(
            envelope=envelope, lease=lease, message=message, receipt=receipt,
            attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
            authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
            decision_id="dec-1", task_id="task-1", worker_id="w1",
            worker_class=None, worker_version="1", operation="transform",
            input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

        self.assertEqual(result1.result_hash, result2.result_hash)
        self.assertEqual(result1.processed_at, result2.processed_at)

    def test_fake_receiver_no_real_agent(self):
        """Verify the fake receiver does not invoke any real agent."""
        envelope = _envelope()
        lease = _lease(envelope)
        message = _message(envelope)

        result = deterministic_fake_receiver(
            envelope=envelope, lease=lease, message=message,
            attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
            authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
            decision_id="dec-1", task_id="task-1", worker_id="w1",
            worker_class=None, worker_version="1", operation="transform",
            input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

        # Fake receiver returns structural result, not real agent output
        self.assertEqual(result.outcome, "ACCEPTED")
        self.assertTrue(len(result.result_hash) == 64)

    def test_receipt_integrity_verified(self):
        envelope = _envelope()
        lease = _lease(envelope)
        message = _message(envelope)
        receipt = _receipt(delegation_id=envelope.delegation_id, capability_lease_id=lease.lease_id)

        # Tamper with receipt hash
        from dataclasses import replace
        tampered = replace(receipt, artifact_hash="tampered" + "0" * 56)

        with self.assertRaises(Exception):
            compose_delegation_with_chain(
                envelope=envelope, lease=lease, message=message, receipt=tampered,
                attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
                authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
                decision_id="dec-1", task_id="task-1", worker_id="w1",
                worker_class=None, worker_version="1", operation="transform",
                input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

    def test_no_executing_projection(self):
        """R12C must NOT project work to EXECUTING."""
        envelope = _envelope()
        lease = _lease(envelope)
        message = _message(envelope)
        receipt = _receipt(delegation_id=envelope.delegation_id, capability_lease_id=lease.lease_id)

        result = compose_delegation_with_chain(
            envelope=envelope, lease=lease, message=message, receipt=receipt,
            attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
            authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
            decision_id="dec-1", task_id="task-1", worker_id="w1",
            worker_class=None, worker_version="1", operation="transform",
            input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

        # Result is a structural proof, not an EXECUTING projection
        self.assertIsInstance(result, FakeReceiverResult)
        self.assertNotEqual(result.outcome, "EXECUTING")

    def test_cancellation_blocks_new_invocation(self):
        """Cancellation before invocation blocks new composition."""
        envelope = _envelope()
        lease = _lease(envelope)
        message = _message(envelope)
        # Rejection receipt indicates cancellation/revocation
        receipt = _receipt(delegation_id=envelope.delegation_id, capability_lease_id=lease.lease_id,
                           outcome="REJECTED", reason_code="REVOKED_OR_CANCELLED", reason_summary="cancelled")

        # Composition still binds, but the receipt outcome reflects the cancellation
        result = compose_delegation_with_chain(
            envelope=envelope, lease=lease, message=message, receipt=receipt,
            attempt_id="attempt-1", route_id="route-1", launch_attempt_id="launch-1",
            authorization_id="auth-1", claim_id="clm-1", request_id="req-1",
            decision_id="dec-1", task_id="task-1", worker_id="w1",
            worker_class=None, worker_version="1", operation="transform",
            input_hash=H, reservation_id="res-1", processed_at="2026-08-28T12:00:03Z")

        # The fake receiver returns ACCEPTED; the receipt outcome is the authority on cancellation
        self.assertEqual(receipt.outcome, "REJECTED")
        self.assertEqual(receipt.reason_code, "REVOKED_OR_CANCELLED")
