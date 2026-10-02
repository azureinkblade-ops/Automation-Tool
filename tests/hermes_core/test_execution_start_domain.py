"""EA-4D.1 focused DOMAIN tests.

Verifies the immutable, hash-bound start-boundary artifacts and their builders
without any persistence, schema change, service, subprocess, network, or
execution-state transition. Capability-negative assertions confirm no
launch/dispatch/enqueue/EXECUTING capability exists in the module.

Mirrors the EA-4C.1 domain-test style. Uses the canonical SHA-256-shaped
placeholder helper for ancestor hashes (64 lowercase hex).
"""

import ast
import inspect
import unittest

from tools.hermes_core.execution_start import (
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    ExecutionLaunchAttempt,
    ExecutionLaunchAttemptStatus,
    ExecutionStartConflictError,
    ExecutionStartExpiredError,
    ExecutionStartIntegrityError,
    ExecutionStartLineageError,
    ExecutionStartOutcome,
    ExecutionStartReservation,
    ExecutionStartReservationStatus,
    ExecutionStartResult,
    ExecutionStartResultError,
    WorkerRuntimeAdapterKind,
    WorkerRuntimeBinding,
    build_execution_launch_attempt,
    build_execution_start_reservation,
    build_execution_start_result,
    build_worker_runtime_binding,
)


def _h(seed):
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _launcher(actor_id="launcher-1", context="ea4d-start"):
    return ExecutionLauncherActor(
        actor_id=actor_id,
        actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
        actor_context=context,
    )


def _reservation_kwargs(**overrides):
    base = dict(
        reservation_id="res-1",
        route_id="route-1",
        route_hash=_h("route"),
        attempt_id="attempt-1",
        attempt_hash=_h("attempt"),
        authorization_id="auth-1",
        authorization_hash=_h("auth"),
        claim_id="claim-1",
        claim_hash=_h("claim"),
        request_id="req-1",
        request_hash=_h("req"),
        decision_id="dec-1",
        decision_hash=_h("dec"),
        task_id="task-1",
        worker_id="w-a",
        worker_class="render-worker",
        worker_version="1",
        operation="run-sandboxed",
        input_hash=_h("in"),
        reserved_at="2026-06-01T00:00:00Z",
        must_start_by="2099-01-01T00:00:00Z",
        launcher_actor=_launcher(),
    )
    base.update(overrides)
    return base


def _launch_kwargs(**overrides):
    base = dict(
        launch_attempt_id="la-1",
        reservation_id="res-1",
        reservation_hash=_h("res"),
        route_id="route-1",
        route_hash=_h("route"),
        attempt_id="attempt-1",
        attempt_hash=_h("attempt"),
        authorization_id="auth-1",
        authorization_hash=_h("auth"),
        task_id="task-1",
        worker_id="w-a",
        worker_class="render-worker",
        worker_version="1",
        operation="run-sandboxed",
        input_hash=_h("in"),
        runtime_binding_id="rb-1",
        runtime_binding_version="1",
        runtime_binding_hash=_h("rb"),
        idempotency_key="idem-1",
        recorded_at="2026-06-01T00:00:00Z",
        must_start_by="2099-01-01T00:00:00Z",
        launcher_actor=_launcher(),
    )
    base.update(overrides)
    return base


class ExecutionStartReservationTests(unittest.TestCase):
    def test_valid_construction_and_hash(self):
        r = build_execution_start_reservation(**_reservation_kwargs())
        self.assertEqual(r.status, ExecutionStartReservationStatus.RESERVED)
        self.assertTrue(r.verify_hash())
        # reconstruct deterministically
        r2 = build_execution_start_reservation(**_reservation_kwargs())
        self.assertEqual(r.artifact_hash, r2.artifact_hash)
        self.assertEqual(r.reservation_id, r2.reservation_id)

    def test_route_id_or_hash_change_alters_hash(self):
        base = build_execution_start_reservation(**_reservation_kwargs())
        other = build_execution_start_reservation(**_reservation_kwargs(route_id="route-2"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)
        other2 = build_execution_start_reservation(**_reservation_kwargs(route_hash=_h("routeX")))
        self.assertNotEqual(base.artifact_hash, other2.artifact_hash)

    def test_attempt_lineage_change_alters_hash(self):
        base = build_execution_start_reservation(**_reservation_kwargs())
        other = build_execution_start_reservation(**_reservation_kwargs(attempt_id="attempt-2"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_authorization_lineage_change_alters_hash(self):
        base = build_execution_start_reservation(**_reservation_kwargs())
        other = build_execution_start_reservation(**_reservation_kwargs(authorization_id="auth-2"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_worker_identity_change_alters_hash(self):
        base = build_execution_start_reservation(**_reservation_kwargs())
        other = build_execution_start_reservation(**_reservation_kwargs(worker_id="w-b"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)
        other2 = build_execution_start_reservation(**_reservation_kwargs(worker_class="other-class"))
        self.assertNotEqual(base.artifact_hash, other2.artifact_hash)
        other3 = build_execution_start_reservation(**_reservation_kwargs(worker_version="2"))
        self.assertNotEqual(base.artifact_hash, other3.artifact_hash)

    def test_operation_input_change_alters_hash(self):
        base = build_execution_start_reservation(**_reservation_kwargs())
        other = build_execution_start_reservation(**_reservation_kwargs(operation="other-op"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)
        other2 = build_execution_start_reservation(**_reservation_kwargs(input_hash=_h("inX")))
        self.assertNotEqual(base.artifact_hash, other2.artifact_hash)

    def test_launcher_actor_change_alters_hash(self):
        base = build_execution_start_reservation(**_reservation_kwargs())
        other = build_execution_start_reservation(**_reservation_kwargs(launcher_actor=_launcher(actor_id="launcher-2")))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)
        other2 = build_execution_start_reservation(**_reservation_kwargs(launcher_actor=_launcher(context="ctx2")))
        self.assertNotEqual(base.artifact_hash, other2.artifact_hash)

    def test_timestamp_deadline_change_alters_hash(self):
        base = build_execution_start_reservation(**_reservation_kwargs())
        other = build_execution_start_reservation(**_reservation_kwargs(reserved_at="2026-06-01T00:00:01Z"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)
        other2 = build_execution_start_reservation(**_reservation_kwargs(must_start_by="2099-01-02T00:00:00Z"))
        self.assertNotEqual(base.artifact_hash, other2.artifact_hash)

    def test_invalid_status_rejected(self):
        # Only RESERVED is authorized; any other status value is rejected.
        with self.assertRaises(ExecutionStartIntegrityError):
            build_execution_start_reservation(
                **_reservation_kwargs(status="STARTED")
            )

    def test_missing_attempt_lineage_rejected(self):
        with self.assertRaises(ExecutionStartLineageError):
            build_execution_start_reservation(**_reservation_kwargs(attempt_id=""))

    def test_non_launcher_actor_rejected(self):
        class _BadActorType:
            value = "SYSTEM"
        bad = ExecutionLauncherActor(
            actor_id="x", actor_type=_BadActorType(), actor_context=None)
        with self.assertRaises(ExecutionStartIntegrityError):
            build_execution_start_reservation(**_reservation_kwargs(launcher_actor=bad))


class ExecutionLaunchAttemptTests(unittest.TestCase):
    def test_valid_construction_and_hash(self):
        a = build_execution_launch_attempt(**_launch_kwargs())
        self.assertEqual(a.status, ExecutionLaunchAttemptStatus.RECORDED)
        self.assertTrue(a.verify_hash())
        a2 = build_execution_launch_attempt(**_launch_kwargs())
        self.assertEqual(a.artifact_hash, a2.artifact_hash)

    def test_reservation_lineage_change_alters_hash(self):
        base = build_execution_launch_attempt(**_launch_kwargs())
        other = build_execution_launch_attempt(**_launch_kwargs(reservation_id="res-2"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)
        other2 = build_execution_launch_attempt(**_launch_kwargs(reservation_hash=_h("resX")))
        self.assertNotEqual(base.artifact_hash, other2.artifact_hash)

    def test_route_lineage_change_alters_hash(self):
        base = build_execution_launch_attempt(**_launch_kwargs())
        other = build_execution_launch_attempt(**_launch_kwargs(route_id="route-2"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_runtime_binding_change_alters_hash(self):
        base = build_execution_launch_attempt(**_launch_kwargs())
        other = build_execution_launch_attempt(**_launch_kwargs(runtime_binding_id="rb-2"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)
        other2 = build_execution_launch_attempt(**_launch_kwargs(idempotency_key="idem-2"))
        self.assertNotEqual(base.artifact_hash, other2.artifact_hash)

    def test_idempotency_key_change_alters_hash(self):
        base = build_execution_launch_attempt(**_launch_kwargs())
        other = build_execution_launch_attempt(**_launch_kwargs(idempotency_key="idem-X"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_invalid_status_rejected(self):
        with self.assertRaises(Exception):
            build_execution_launch_attempt(
                **_launch_kwargs(status=ExecutionLaunchAttemptStatus("LAUNCHED")))


class ExecutionStartResultTests(unittest.TestCase):
    def test_started_valid(self):
        r = build_execution_start_result(
            start_result_id="sr-1",
            launch_attempt_id="la-1",
            launch_attempt_hash=_h("la"),
            reservation_id="res-1",
            reservation_hash=_h("res"),
            route_id="route-1",
            route_hash=_h("route"),
            task_id="task-1",
            worker_id="w-a",
            worker_version="1",
            outcome=ExecutionStartOutcome.STARTED,
            recorded_at="2026-06-01T00:00:00Z",
            runtime_run_id="run-1",
        )
        self.assertEqual(r.outcome, ExecutionStartOutcome.STARTED)
        self.assertTrue(r.verify_hash())

    def test_failed_valid(self):
        r = build_execution_start_result(
            start_result_id="sr-2",
            launch_attempt_id="la-1",
            launch_attempt_hash=_h("la"),
            reservation_id="res-1",
            reservation_hash=_h("res"),
            route_id="route-1",
            route_hash=_h("route"),
            task_id="task-1",
            worker_id="w-a",
            worker_version="1",
            outcome=ExecutionStartOutcome.FAILED,
            recorded_at="2026-06-01T00:00:00Z",
            error_code="WORKER_REJECTED",
        )
        self.assertEqual(r.outcome, ExecutionStartOutcome.FAILED)
        self.assertTrue(r.verify_hash())

    def test_unknown_valid(self):
        r = build_execution_start_result(
            start_result_id="sr-3",
            launch_attempt_id="la-1",
            launch_attempt_hash=_h("la"),
            reservation_id="res-1",
            reservation_hash=_h("res"),
            route_id="route-1",
            route_hash=_h("route"),
            task_id="task-1",
            worker_id="w-a",
            worker_version="1",
            outcome=ExecutionStartOutcome.UNKNOWN,
            recorded_at="2026-06-01T00:00:00Z",
        )
        self.assertEqual(r.outcome, ExecutionStartOutcome.UNKNOWN)
        self.assertTrue(r.verify_hash())

    def test_invalid_outcome_rejected(self):
        # The outcome enum is closed; an unknown value cannot be constructed,
        # which is the domain-enforced boundary (no silent invalid outcome).
        with self.assertRaises(ValueError):
            ExecutionStartOutcome("BOUNCED")
        # The builder also guards against any non-member value via its explicit
        # membership check. Use a sentinel with the right .value shape.
        class _Bounced:
            value = "BOUNCED"
        with self.assertRaises(ExecutionStartResultError):
            build_execution_start_result(
                start_result_id="sr-4",
                launch_attempt_id="la-1", launch_attempt_hash=_h("la"),
                reservation_id="res-1", reservation_hash=_h("res"), route_id="route-1",
                route_hash=_h("route"), task_id="task-1", worker_id="w-a", worker_version="1",
                outcome=_Bounced(), recorded_at="2026-06-01T00:00:00Z")

    def test_launch_attempt_lineage_change_alters_hash(self):
        base = build_execution_start_result(
            start_result_id="sr-1", launch_attempt_id="la-1", launch_attempt_hash=_h("la"),
            reservation_id="res-1", reservation_hash=_h("res"), route_id="route-1",
            route_hash=_h("route"), task_id="task-1", worker_id="w-a", worker_version="1",
            outcome=ExecutionStartOutcome.STARTED, recorded_at="2026-06-01T00:00:00Z",
            runtime_run_id="run-1")
        other = build_execution_start_result(
            start_result_id="sr-1", launch_attempt_id="la-2", launch_attempt_hash=_h("laX"),
            reservation_id="res-1", reservation_hash=_h("res"), route_id="route-1",
            route_hash=_h("route"), task_id="task-1", worker_id="w-a", worker_version="1",
            outcome=ExecutionStartOutcome.STARTED, recorded_at="2026-06-01T00:00:00Z",
            runtime_run_id="run-1")
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_runtime_run_id_change_alters_hash_when_present(self):
        base = build_execution_start_result(
            start_result_id="sr-1", launch_attempt_id="la-1", launch_attempt_hash=_h("la"),
            reservation_id="res-1", reservation_hash=_h("res"), route_id="route-1",
            route_hash=_h("route"), task_id="task-1", worker_id="w-a", worker_version="1",
            outcome=ExecutionStartOutcome.STARTED, recorded_at="2026-06-01T00:00:00Z",
            runtime_run_id="run-1")
        other = build_execution_start_result(
            start_result_id="sr-1", launch_attempt_id="la-1", launch_attempt_hash=_h("la"),
            reservation_id="res-1", reservation_hash=_h("res"), route_id="route-1",
            route_hash=_h("route"), task_id="task-1", worker_id="w-a", worker_version="1",
            outcome=ExecutionStartOutcome.STARTED, recorded_at="2026-06-01T00:00:00Z",
            runtime_run_id="run-2")
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)


class WorkerRuntimeBindingTests(unittest.TestCase):
    def _build(self, **overrides):
        base = dict(
            runtime_binding_id="rb-1",
            worker_id="w-a",
            worker_version="1",
            worker_class="render-worker",
            adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
            adapter_version="1",
            configuration_reference="cfg://local/w-a",
            configuration_hash=_h("cfg"),
            allowed_operations=["run-sandboxed"],
            supports_idempotency=True,
            enabled=True,
        )
        base.update(overrides)
        return build_worker_runtime_binding(**base)

    def test_valid_construction_and_hash(self):
        b = self._build()
        self.assertTrue(b.verify_hash())
        self.assertTrue(b.supports_idempotency)
        self.assertTrue(b.enabled)

    def test_worker_identity_change_alters_hash(self):
        base = self._build()
        self.assertNotEqual(base.artifact_hash, self._build(worker_id="w-b").artifact_hash)
        self._build(worker_class="other-class")  # must not raise; hash differs
        self.assertNotEqual(base.artifact_hash, self._build(worker_class="other-class").artifact_hash)

    def test_adapter_identity_change_alters_hash(self):
        base = self._build()
        other = self._build(adapter_kind=WorkerRuntimeAdapterKind.MODEL_RUNTIME_ADAPTER)
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_configuration_hash_change_alters_hash(self):
        base = self._build()
        other = self._build(configuration_hash=_h("cfgX"))
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_operation_set_change_alters_hash(self):
        base = self._build(allowed_operations=["run-sandboxed"])
        other = self._build(allowed_operations=["run-sandboxed", "other-op"])
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_disabled_binding_represented(self):
        b = self._build(enabled=False)
        self.assertFalse(b.enabled)
        self.assertTrue(b.verify_hash())

    def test_idempotency_capability_represented(self):
        b = self._build(supports_idempotency=True)
        self.assertTrue(b.supports_idempotency)

    def test_duplicate_operations_canonicalized(self):
        b = self._build(allowed_operations=["run-sandboxed", "run-sandboxed", "other-op"])
        self.assertEqual(sorted(b.allowed_operations), ["other-op", "run-sandboxed"])


class ActorAndCapabilityBoundaryTests(unittest.TestCase):
    def test_system_launcher_valid(self):
        a = ExecutionLauncherActorType.SYSTEM_LAUNCHER
        self.assertEqual(a.value, "SYSTEM_LAUNCHER")

    def test_unsupported_launcher_actor_rejected_by_builder(self):
        class _BadActorType:
            value = "SYSTEM"
        bad = ExecutionLauncherActor(
            actor_id="x", actor_type=_BadActorType(), actor_context=None)
        with self.assertRaises(ExecutionStartIntegrityError):
            build_execution_start_reservation(**_reservation_kwargs(launcher_actor=bad))

    def test_no_subprocess_capability(self):
        import tools.hermes_core.execution_start as mod

        src = inspect.getsource(mod)
        tree = ast.parse(src)
        # Negative prose mentions are acceptable (design section 46). We assert
        # there is NO import of, and NO callable use of, any forbidden capability.
        forbidden_imports = {
            "subprocess", "os", "requests", "httpx", "urllib",
            "playwright", "sqlite3",
        }
        # Check imports.
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imported.add(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertFalse(
            forbidden_imports & imported,
            f"forbidden import present in EA-4D.1 domain module: {forbidden_imports & imported}")
        # Check callable use of forbidden names (any Name/CALL site).
        forbidden_calls = {
            "subprocess", "Popen", "os", "system", "shell", "CreateProcess",
            "Start-Process", "requests", "httpx", "urllib", "Ollama", "Playwright",
            "queue", "put", "enqueue", "dispatch", "launch_worker",
        }
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        used = names | attrs
        self.assertFalse(
            forbidden_calls & used,
            f"forbidden capability token used in EA-4D.1 domain module: {forbidden_calls & used}")
        # No function named for worker launch/execution/dispatch exists.
        func_names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef,))}
        self.assertFalse(
            {"start_worker", "execute_worker", "launch_worker", "dispatch", "enqueue"} & func_names,
            f"forbidden capability function present: {func_names & forbidden_calls}")

    def test_no_executing_transition_function_exists(self):
        import tools.hermes_core.execution_start as mod

        self.assertFalse(hasattr(mod, "start_worker"))
        self.assertFalse(hasattr(mod, "execute_worker"))
        self.assertFalse(hasattr(mod, "launch_worker"))
        # No enum/string EXECUTING is defined as a state here (it is a later EA-4D slice).
        self.assertNotIn("EXECUTING", dir(mod))


if __name__ == "__main__":
    unittest.main()
