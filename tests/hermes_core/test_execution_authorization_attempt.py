"""Focused EA-4B.1 domain tests for ExecutionAttempt.

These tests prove the EA-4B DOMAIN MODEL only. No persistence, no claim
consumption service, no worker behavior, no execution transitions.
"""
from __future__ import annotations

import copy
import unittest

from tools.hermes_core.execution_authorization import (
    ATTEMPT_ARTIFACT_VERSION,
    ExecutionAttempt,
    ExecutionAttemptActor,
    ExecutionAttemptConflictError,
    ExecutionAttemptError,
    ExecutionAttemptLineageError,
    ExecutionAttemptLimitError,
    ExecutionAttemptNotFoundError,
    ExecutionAttemptStatus,
    ExecutionAuthorizationValidationError,
    build_execution_attempt,
    reconstruct_attempt,
)


def make_attempt_actor(**overrides) -> ExecutionAttemptActor:
    defaults = dict(
        actor_id="runtime-orchestrator",
        actor_type="SYSTEM",
        actor_context="node-1",
    )
    defaults.update(overrides)
    return ExecutionAttemptActor(**defaults)


def make_attempt(**overrides) -> ExecutionAttempt:
    defaults = dict(
        authorization_id="execution-authorization-" + "a" * 16,
        authorization_hash="a" * 64,
        request_id="execution-authorization-request-" + "b" * 16,
        request_hash="b" * 64,
        decision_id="execution-authorization-decision-" + "c" * 16,
        decision_hash="c" * 64,
        claim_id="execution-authorization-claim-" + "d" * 16,
        claim_hash="d" * 64,
        task_id="task-1",
        attempt_number=1,
        attempt_actor=make_attempt_actor(),
        attempt_requested_at="2026-08-12T21:30:00Z",
        attempt_recorded_at="2026-08-12T21:30:01Z",
        claim_expires_at="2026-08-12T22:00:00Z",
        must_start_by="2026-08-12T21:35:00Z",
        input_hash="e" * 64,
        operation="run-sandboxed",
        worker_class="restricted-sandbox",
        status=ExecutionAttemptStatus.RECORDED,
    )
    defaults.update(overrides)
    return build_execution_attempt(**defaults)


class TestExecutionAttemptDomain(unittest.TestCase):
    """EA-4B.1 domain-level coverage for ExecutionAttempt."""

    def test_happy_build_and_verify(self):
        attempt = make_attempt()
        self.assertIsInstance(attempt, ExecutionAttempt)
        self.assertTrue(attempt.verify_hash())
        self.assertEqual(attempt.status, ExecutionAttemptStatus.RECORDED)
        self.assertEqual(attempt.artifact_version, ATTEMPT_ARTIFACT_VERSION)
        self.assertEqual(attempt.attempt_number, 1)

    def test_all_required_fields_present(self):
        attempt = make_attempt()
        # Verify every required field exists and is non-empty
        self.assertTrue(attempt.attempt_id)
        self.assertTrue(attempt.authorization_id)
        self.assertTrue(attempt.authorization_hash)
        self.assertTrue(attempt.request_id)
        self.assertTrue(attempt.request_hash)
        self.assertTrue(attempt.decision_id)
        self.assertTrue(attempt.decision_hash)
        self.assertTrue(attempt.claim_id)
        self.assertTrue(attempt.claim_hash)
        self.assertTrue(attempt.task_id)
        self.assertTrue(attempt.attempt_number)
        self.assertTrue(attempt.attempt_actor_id)
        self.assertTrue(attempt.attempt_actor_type)
        self.assertTrue(attempt.attempt_requested_at)
        self.assertTrue(attempt.attempt_recorded_at)
        self.assertTrue(attempt.claim_expires_at)
        self.assertTrue(attempt.must_start_by)
        self.assertTrue(attempt.input_hash)
        self.assertTrue(attempt.operation)
        self.assertTrue(attempt.worker_class)
        self.assertTrue(attempt.status)
        self.assertTrue(attempt.artifact_version)
        self.assertTrue(attempt.artifact_hash)

    def test_immutable_frozen(self):
        attempt = make_attempt()
        with self.assertRaises(Exception):
            attempt.attempt_number = 99  # type: ignore[misc]

    def test_status_is_recorded(self):
        attempt = make_attempt()
        self.assertEqual(attempt.status, ExecutionAttemptStatus.RECORDED)
        self.assertNotEqual(attempt.status, "EXECUTING")


class TestDeterministicHashing(unittest.TestCase):
    def test_same_inputs_same_hash(self):
        a = make_attempt()
        b = make_attempt()
        self.assertEqual(a.artifact_hash, b.artifact_hash)
        self.assertEqual(a.to_canonical_dict(), b.to_canonical_dict())

    def test_different_attempt_number_different_hash(self):
        a = make_attempt(attempt_number=1)
        b = make_attempt(attempt_number=2)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_claim_id_different_hash(self):
        a = make_attempt()
        b = make_attempt(claim_id="execution-authorization-claim-" + "e" * 16)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_claim_hash_different_hash(self):
        a = make_attempt()
        b = make_attempt(claim_hash="f" * 64)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_authorization_id_different_hash(self):
        a = make_attempt()
        b = make_attempt(authorization_id="execution-authorization-" + "b" * 16)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_authorization_hash_different_hash(self):
        a = make_attempt()
        b = make_attempt(authorization_hash="f" * 64)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_request_id_different_hash(self):
        a = make_attempt()
        b = make_attempt(request_id="execution-authorization-request-" + "f" * 16)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_request_hash_different_hash(self):
        a = make_attempt()
        b = make_attempt(request_hash="f" * 64)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_decision_id_different_hash(self):
        a = make_attempt()
        b = make_attempt(decision_id="execution-authorization-decision-" + "f" * 16)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_decision_hash_different_hash(self):
        a = make_attempt()
        b = make_attempt(decision_hash="f" * 64)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_task_id_different_hash(self):
        a = make_attempt()
        b = make_attempt(task_id="task-2")
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_actor_id_different_hash(self):
        a = make_attempt()
        b = make_attempt(attempt_actor=make_attempt_actor(actor_id="other"))
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_actor_type_different_hash(self):
        a = make_attempt()
        b = make_attempt(attempt_actor=make_attempt_actor(actor_type="HUMAN"))
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_actor_context_different_hash(self):
        a = make_attempt()
        b = make_attempt(attempt_actor=make_attempt_actor(actor_context="node-2"))
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_operation_different_hash(self):
        a = make_attempt()
        b = make_attempt(operation="run-embedded")
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_worker_class_different_hash(self):
        a = make_attempt()
        b = make_attempt(worker_class="unrestricted-worker")
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_input_hash_different_hash(self):
        a = make_attempt()
        b = make_attempt(input_hash="a" * 64)
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_must_start_by_different_hash(self):
        a = make_attempt()
        b = make_attempt(must_start_by="2026-08-12T21:40:00Z")
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_attempt_requested_at_different_hash(self):
        a = make_attempt()
        b = make_attempt(attempt_requested_at="2026-08-12T21:31:00Z")
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_different_attempt_recorded_at_different_hash(self):
        a = make_attempt()
        b = make_attempt(attempt_recorded_at="2026-08-12T21:32:00Z")
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_hash_excludes_stored_hash(self):
        attempt = make_attempt()
        digest = attempt.canonical_json()
        self.assertNotIn("artifact_hash", digest)


class TestTamperDetection(unittest.TestCase):
    def test_tamper_detected_via_reconstructed_dict(self):
        attempt = make_attempt()
        payload = attempt.to_canonical_dict()
        tampered = copy.deepcopy(payload)
        tampered["operation"] = "mutated-op"
        self.assertNotEqual(
            _rehash(tampered), attempt.artifact_hash
        )

    def test_tamper_attempt_number_changes_hash(self):
        attempt = make_attempt()
        payload = attempt.to_canonical_dict()
        tampered = copy.deepcopy(payload)
        tampered["attempt_number"] = 99
        self.assertNotEqual(
            _rehash(tampered), attempt.artifact_hash
        )

    def test_tamper_actor_id_changes_hash(self):
        attempt = make_attempt()
        payload = attempt.to_canonical_dict()
        tampered = copy.deepcopy(payload)
        tampered["attempt_actor_id"] = "mutated-actor"
        self.assertNotEqual(
            _rehash(tampered), attempt.artifact_hash
        )

    def test_tamper_must_start_by_changes_hash(self):
        attempt = make_attempt()
        payload = attempt.to_canonical_dict()
        tampered = copy.deepcopy(payload)
        tampered["must_start_by"] = "2027-01-01T00:00:00Z"
        self.assertNotEqual(
            _rehash(tampered), attempt.artifact_hash
        )


def _rehash(d: dict) -> str:
    import hashlib
    from tools.hermes_core.hashing import canonical_json
    return hashlib.sha256(canonical_json(d).encode("utf-8")).hexdigest()


class TestReconstruction(unittest.TestCase):
    def test_round_trip_preserves_identity(self):
        attempt = make_attempt()
        payload = attempt.to_canonical_dict()
        payload["artifact_hash"] = attempt.artifact_hash
        rebuilt = reconstruct_attempt(payload)
        self.assertEqual(rebuilt.attempt_id, attempt.attempt_id)
        self.assertEqual(rebuilt.authorization_id, attempt.authorization_id)
        self.assertEqual(rebuilt.claim_id, attempt.claim_id)
        self.assertEqual(rebuilt.task_id, attempt.task_id)
        self.assertEqual(rebuilt.attempt_number, attempt.attempt_number)
        self.assertEqual(rebuilt.artifact_hash, attempt.artifact_hash)
        self.assertTrue(rebuilt.verify_hash())

    def test_reconstruction_restores_actor(self):
        attempt = make_attempt()
        payload = attempt.to_canonical_dict()
        payload["artifact_hash"] = attempt.artifact_hash
        rebuilt = reconstruct_attempt(payload)
        self.assertEqual(rebuilt.attempt_actor_id, attempt.attempt_actor_id)
        self.assertEqual(rebuilt.attempt_actor_type, attempt.attempt_actor_type)
        self.assertEqual(rebuilt.attempt_actor_context, attempt.attempt_actor_context)


class TestNegativeValidation(unittest.TestCase):
    def test_empty_authorization_id_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(authorization_id="")

    def test_malformed_authorization_hash_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(authorization_hash="not-a-hash")

    def test_empty_request_id_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(request_id="")

    def test_malformed_request_hash_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(request_hash="zzz")

    def test_empty_claim_id_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(claim_id="")

    def test_malformed_claim_hash_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(claim_hash="zzz")

    def test_empty_task_id_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(task_id="")

    def test_attempt_number_zero_rejected(self):
        with self.assertRaises(ExecutionAttemptError):
            make_attempt(attempt_number=0)

    def test_attempt_number_negative_rejected(self):
        with self.assertRaises(ExecutionAttemptError):
            make_attempt(attempt_number=-1)

    def test_empty_actor_id_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(attempt_actor=make_attempt_actor(actor_id=""))

    def test_empty_actor_type_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(attempt_actor=make_attempt_actor(actor_type=""))

    def test_empty_operation_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(operation="")

    def test_malformed_input_hash_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(input_hash="not-a-hash")

    def test_non_utc_attempt_requested_at_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(attempt_requested_at="2026-08-12T21:30:00")

    def test_non_utc_must_start_by_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(must_start_by="not-a-time")

    def test_invalid_worker_class_none_allowed(self):
        attempt = make_attempt(worker_class=None)
        self.assertIsNone(attempt.worker_class)

    def test_empty_worker_class_rejected(self):
        with self.assertRaises((ExecutionAttemptError, ExecutionAuthorizationValidationError)):
            make_attempt(worker_class="")

    def test_attempt_id_format_valid(self):
        attempt = make_attempt()
        self.assertTrue(attempt.attempt_id.startswith("execution-authorization-attempt-"))


class TestCapabilityBoundary(unittest.TestCase):
    """EA-4B must prove absence of execution/runtime behavior."""

    def test_no_execution_transition(self):
        # No status other than RECORDED should exist
        member_names = [m.name for m in ExecutionAttemptStatus]
        self.assertEqual(member_names, ["RECORDED"])

    def test_no_worker_launch_artifacts(self):
        import importlib
        mod = importlib.import_module("tools.hermes_core.execution_authorization")
        # Ensure no worker-launch identifiers exist as classes/functions
        forbidden = [
            "WorkerRouter", "launch_worker", "enqueue", "dispatch",
            "subprocess", "EXECUTING", "RUNNING", "STARTED", "Popen",
            "execute", "run_process",
        ]
        violations = []
        for name in dir(mod):
            if name.startswith("_"):
                continue
            for f in forbidden:
                if f in name:
                    violations.append(name)
        self.assertEqual(
            violations, [],
            msg=f"forbidden execution identifiers found: {violations}",
        )

    def test_attempt_is_not_executing(self):
        attempt = make_attempt()
        self.assertNotEqual(attempt.status, "EXECUTING")
        self.assertNotEqual(attempt.status, "RUNNING")
        self.assertNotEqual(attempt.status, "STARTED")


if __name__ == "__main__":
    unittest.main()
