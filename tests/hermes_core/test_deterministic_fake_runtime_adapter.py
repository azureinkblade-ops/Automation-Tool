"""EA-4D.3C deterministic fake runtime adapter behavior tests.

Covers the full scripted matrix required by the authorization packet:
STARTED / FAILED / UNKNOWN, timeout-after-send -> UNKNOWN, ambiguous exception
-> UNKNOWN, definitive pre-send rejection -> FAILED, stable runtime_run_id for
same key, same-key replay (no duplicate logical run), different key -> distinct
logical run, conflicting same-key + different lineage -> typed conflict,
invocation/logical-run counts, and the four lookup outcomes.

Invariant preserved: LAUNCH_ATTEMPT_RECORDED != WORKER STARTED. The fake never
starts a real worker, never persists, never projects EXECUTING.
"""

import hashlib
import unittest

from tools.hermes_core.execution_start import (
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    ExecutionLaunchAttemptStatus,
    WorkerRuntimeAdapterKind,
    WorkerRuntimeBinding,
    build_execution_launch_attempt,
    build_worker_runtime_binding,
)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeAdapterConflictError,
    RuntimeAdapterValidationError,
    RuntimeLaunchOutcome,
    RuntimeLookupOutcome,
)
from tools.hermes_core.deterministic_fake_runtime_adapter import (
    DeterministicFakeRuntimeAdapter,
    FakeLaunchScript,
    _stable_run_id,
)


def _binding():
    return build_worker_runtime_binding(
        runtime_binding_id="binding-1",
        worker_id="worker-1",
        worker_version="1",
        worker_class="run-sandbox",
        adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
        adapter_version="1",
        configuration_reference="hermes-worker-local-v1",
        configuration_hash="b" * 64,
        allowed_operations=["run-sandbox"],
        supports_idempotency=True,
        enabled=True,
    )


def _attempt(idempotency_key="k-1", route_id="route-1", reservation_hash="h" * 64):
    return build_execution_launch_attempt(
        launch_attempt_id="latch-1",
        reservation_id="res-1",
        reservation_hash=reservation_hash,
        route_id=route_id,
        route_hash="r" * 64,
        attempt_id="att-1",
        attempt_hash="a" * 64,
        authorization_id="auth-1",
        authorization_hash="z" * 64,
        task_id="task-1",
        worker_id="worker-1",
        worker_class="run-sandbox",
        worker_version="1",
        operation="run-sandbox",
        input_hash="0" * 64,
        runtime_binding_id="binding-1",
        runtime_binding_version="1",
        runtime_binding_hash="b" * 64,
        idempotency_key=idempotency_key,
        recorded_at="2024-01-01T00:00:00Z",
        must_start_by="2024-01-02T00:00:00Z",
        launcher_actor=ExecutionLauncherActor(
            actor_id="launcher-1",
            actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
            actor_context=None,
        ),
        status=ExecutionLaunchAttemptStatus.RECORDED,
    )


class FakeScriptedOutcomeTests(unittest.TestCase):
    def test_scripted_started(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        res = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)
        self.assertTrue(res.runtime_run_id)

    def test_scripted_failed(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.FAILED,
            error_code="REJECT", error_summary="denied"))
        res = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.FAILED)
        self.assertIsNone(res.runtime_run_id)
        self.assertEqual(res.error_code, "REJECT")

    def test_scripted_unknown(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.UNKNOWN))
        res = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)

    def test_timeout_after_send_is_unknown(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(timeout_after_send=True))
        res = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)
        self.assertEqual(res.error_code, "ACK_LOST")

    def test_lost_response_is_unknown(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(lost_response=True))
        res = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)

    def test_ambiguous_post_delivery_exception_is_unknown(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(raise_post_delivery=True))
        res = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)

    def test_definitive_pre_delivery_rejection_is_failed(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(raise_pre_delivery=True))
        with self.assertRaises(RuntimeAdapterValidationError):
            a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")


class IdempotencyTests(unittest.TestCase):
    def test_stable_runtime_run_id_for_same_key(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        r1 = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        r2 = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(r1.runtime_run_id, r2.runtime_run_id)
        self.assertEqual(r1.runtime_run_id, _stable_run_id("k-1"))

    def test_same_key_replay_no_duplicate_logical_run(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(a.logical_run_count, 1)
        self.assertEqual(a.invocation_count, 3)

    def test_different_key_distinct_logical_run(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        a.launch(binding=_binding(), launch_attempt=_attempt(idempotency_key="k-2"),
                 idempotency_key="k-2")
        self.assertEqual(a.logical_run_count, 2)
        self.assertNotEqual(_stable_run_id("k-1"), _stable_run_id("k-2"))

    def test_same_key_conflicting_lineage_is_typed_conflict(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        with self.assertRaises(RuntimeAdapterConflictError):
            a.launch(
                binding=_binding(),
                launch_attempt=_attempt(reservation_hash="x" * 64),
                idempotency_key="k-1")

    def test_caller_cannot_override_idempotency_key(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        with self.assertRaises(RuntimeAdapterValidationError):
            a.launch(
                binding=_binding(),
                launch_attempt=_attempt(idempotency_key="k-1"),
                idempotency_key="k-EVIL")

    def test_no_random_key_generation(self):
        # The run id is a pure deterministic digest of the key; identical keys
        # yield identical ids across independent adapter instances.
        a1 = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        a2 = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        r1 = a1.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        r2 = a2.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(r1.runtime_run_id, r2.runtime_run_id)

    def test_replay_determinism_scripted_unknown(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.UNKNOWN))
        r1 = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        r2 = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(r1.outcome, r2.outcome)
        self.assertEqual(r1.runtime_run_id, r2.runtime_run_id)


class PositiveAcknowledgementTests(unittest.TestCase):
    def test_started_requires_positive_acknowledgement(self):
        # STARTED is only produced when the fake scripts STARTED; a no-exception
        # return with FAILED/UNKNOWN does not imply STARTED.
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.FAILED))
        res = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertNotEqual(res.outcome, RuntimeLaunchOutcome.STARTED)

    def test_repeated_same_key_started_same_run_id(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        r1 = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        r2 = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(r1.runtime_run_id, r2.runtime_run_id)


class UnknownTests(unittest.TestCase):
    def test_unknown_does_not_trigger_relaunch(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.UNKNOWN))
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        # a second call must NOT create a new logical run
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(a.logical_run_count, 1)

    def test_unknown_never_becomes_failed_for_absent_ack(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.UNKNOWN))
        res = a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)


class LookupTests(unittest.TestCase):
    def test_lookup_found_started(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        res = a.lookup("k-1")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.FOUND_STARTED)
        self.assertTrue(res.runtime_run_id)

    def test_lookup_found_failed(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.FAILED, error_code="REJECT"))
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        res = a.lookup("k-1")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.FOUND_FAILED)
        self.assertEqual(res.error_code, "REJECT")

    def test_lookup_not_found_authoritative(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        res = a.lookup("never-seen-key")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE)

    def test_lookup_unknown_scripted(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            lookup_outcome=RuntimeLookupOutcome.UNKNOWN))
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        res = a.lookup("k-1")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.UNKNOWN)

    def test_lookup_repeated_deterministic(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        a.launch(binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(a.lookup("k-1").outcome, RuntimeLookupOutcome.FOUND_STARTED)
        self.assertEqual(a.lookup("k-1").outcome, RuntimeLookupOutcome.FOUND_STARTED)

    def test_lookup_never_creates_work(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        before = a.logical_run_count
        a.lookup("brand-new-key")
        self.assertEqual(a.logical_run_count, before)

    def test_lookup_never_mutates_launch_attempt(self):
        attempt = _attempt()
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        a.launch(binding=_binding(), launch_attempt=attempt, idempotency_key="k-1")
        before = (attempt.launch_attempt_id, attempt.status.value)
        a.lookup("k-1")
        self.assertEqual((attempt.launch_attempt_id, attempt.status.value), before)


class ModestConcurrencyTests(unittest.TestCase):
    def test_ten_callers_same_key_one_logical_run(self):
        a = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        binding = _binding()
        attempt = _attempt()
        for _ in range(10):
            res = a.launch(binding=binding, launch_attempt=attempt, idempotency_key="k-1")
            self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)
        self.assertEqual(a.logical_run_count, 1)
        self.assertEqual(a.invocation_count, 10)


if __name__ == "__main__":
    unittest.main()
