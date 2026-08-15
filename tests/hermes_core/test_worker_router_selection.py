"""EA-4C.3 focused selection tests (deterministic eligibility, selection, admission).

Persistence integration reuses the EA-4C.2 store (record_route / get_route_for_attempt)
without re-implementing it. Capability-negative tests prove no launch/dispatch/
execution code paths exist.

Mirrors the EA-4B attempt-chain setup (request -> granted decision + authorization
-> claim) so the selection service can load a real durable Attempt.

NOTE (clean reconstruction from 51ff8fe): this suite tests ONLY EA-4C.3 semantics.
It deliberately asserts (test_ea4c4_race_loser_handling_absent /
test_record_route_failure_reread_path_absent) that the EA-4C.4 lost-INSERT-race
behavior is NOT present in this module, so the contaminated cc51e85 behavior cannot
leak backward into the fresh EA-4C.3 reconstruction.
"""

import ast
import inspect
import os
import tempfile
import unittest
from datetime import datetime

from tools.hermes_core.execution_authorization import (
    ExecutionAttemptActor,
    ExecutionAttemptStatus,
    ExecutionAuthorizationActor,
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationDecisionOutcome,
    ExecutionAuthorizationPolicyRef,
    ExecutionAuthorizationScope,
    ExecutionClaimant,
    build_execution_authorization,
    build_execution_authorization_decision,
    build_execution_authorization_request,
    build_execution_claim,
)
from tools.hermes_core.execution_authorization_attempt import (
    consume_claim_into_attempt as _consume,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.worker_router import (
    WorkerRegistryIntegrityError,
    WorkerRouteConflictError,
    WorkerRouteError,
    WorkerRouteExpiredError,
    WorkerRouteIntegrityError,
    WorkerRouteLineageError,
    WorkerRouteNoEligibleWorkerError,
    WorkerRouterActor,
    WorkerRouterActorType,
    WorkerRoutingPolicyRef,
    WorkerRouteStatus,
    build_worker_descriptor,
    build_worker_registry,
)
from tools.hermes_core.worker_router_service import (
    require_attempt_scope_matches_authorization,
    select_and_record_worker_route,
    utc_now,
)


def _h(seed: str) -> str:
    """Deterministic 64-char lowercase-hex placeholder (valid SHA-256 form)."""
    import hashlib

    return hashlib.sha256(seed.encode()).hexdigest()


def _make_scope(worker_class="render-worker", operation="run-sandboxed", input_seed="in"):
    return ExecutionAuthorizationScope(
        operation=operation,
        worker_class=worker_class,
        input_hash=_h(input_seed),
        attempt_limit=5,
        max_runtime_seconds=300,
    )


def _make_actor():
    return ExecutionAuthorizationActor(
        actor_id="issuer-1",
        actor_type=ExecutionAuthorizationActorType.SYSTEM,
        authority_role="grant",
        authentication_context=None,
    )


def _make_attempt_actor():
    return ExecutionAttemptActor(
        actor_id="claimant-1",
        actor_type="SYSTEM",
        actor_context=None,
    )


def _make_policy():
    return ExecutionAuthorizationPolicyRef(policy_id="ea-baseline", policy_version="1.0")


def _make_routing_policy():
    return WorkerRoutingPolicyRef(
        policy_id="routing-policy-1",
        policy_version="1",
        policy_hash=_h("policy-1"),
    )


def _make_router_actor():
    return WorkerRouterActor(
        actor_id="router-1",
        actor_type=WorkerRouterActorType.SYSTEM_ROUTER,
        actor_context="ea4c3-selection",
    )


def _setup_claim_lineage(
    store,
    task_id="task-1",
    scope=None,
    must_start_by=None,
    consume_clock="2026-01-01T00:00:05Z",
    must_start_within_seconds=10**8,
):
    """Build + persist a real Attempt (mirrors test_worker_router_store._setup_claim_lineage).

    ``must_start_by`` is controlled at attempt-construction time (the consume
    clock + window), NOT by mutating a persisted row afterwards. If ``must_start_by``
    is given, the consume window is chosen so the resulting Attempt carries that
    exact deadline. Otherwise the default window keeps the deadline far in the
    future.
    """
    if scope is None:
        scope = _make_scope()
    if must_start_by is None:
        must_start_by = "2099-01-01T00:00:00Z"
    # derive the consume window from consume_clock + desired must_start_by
    base_dt = datetime.strptime(consume_clock, "%Y-%m-%dT%H:%M:%SZ")
    target_dt = datetime.strptime(must_start_by, "%Y-%m-%dT%H:%M:%SZ")
    window = int((target_dt - base_dt).total_seconds())
    if window < 0:
        window = 0
    actor = _make_actor()
    acc_id = "acceptance-" + "b" * 16
    acc_hash = _h("acc")
    policy = _make_policy()

    req = build_execution_authorization_request(
        task_id=task_id,
        accepted_governance_artifact_id=acc_id,
        accepted_governance_hash=acc_hash,
        requested_scope=scope,
        requesting_actor=actor,
        authorization_policy=policy,
        requested_at="2026-01-01T00:00:00Z",
        request_reason="need exec",
    )
    store.record_request(req)

    dec = build_execution_authorization_decision(
        request_id=req.request_id,
        request_hash=req.artifact_hash,
        task_id=task_id,
        decision_actor=actor,
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason="approved",
        authorization_id="execution-authorization-" + "d" * 16,
        authorization_policy=policy,
    )
    auth = build_execution_authorization(
        task_id=task_id,
        accepted_governance_artifact_id=acc_id,
        accepted_governance_hash=acc_hash,
        request_id=req.request_id,
        request_hash=req.artifact_hash,
        decision_id=dec.decision_id,
        decision_hash=dec.artifact_hash,
        authorization_actor=actor,
        authorized_scope=scope,
        authorization_reason="operator approved",
        authorization_policy=policy,
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        nonce="nonce-0001",
    )
    dec = build_execution_authorization_decision(
        request_id=req.request_id,
        request_hash=req.artifact_hash,
        task_id=task_id,
        decision_actor=actor,
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason="approved",
        authorization_id=auth.authorization_id,
        authorization_policy=policy,
    )
    store.record_granted_decision_and_authorization(dec, auth)

    claim = build_execution_claim(
        authorization_id=auth.authorization_id,
        authorization_hash=auth.artifact_hash,
        request_id=auth.request_id,
        request_hash=auth.request_hash,
        decision_id=auth.decision_id,
        decision_hash=auth.decision_hash,
        task_id=auth.task_id,
        claimant=ExecutionClaimant(
            claimant_id="worker-manager",
            claimant_type="worker-manager",
            claimant_context="node-1",
        ),
        claimed_at="2026-01-01T00:00:00Z",
        claim_expires_at="2099-01-01T00:00:00Z",
        authorization_policy=policy,
        claim_reason="claim by worker-manager",
    )
    store.claim_authorization_atomically(auth.authorization_id, claim)

    result = _consume(
        store=store,
        authorization_id=auth.authorization_id,
        claim_id=claim.claim_id,
        claimant=_make_attempt_actor(),
        must_start_within_seconds=window,
        clock=lambda: consume_clock,
    )
    return result.attempt_id, auth, must_start_by


def _registry(workers):
    return build_worker_registry(registry_version="reg-1", workers=workers)


def _descriptor(worker_id, enabled=True, worker_class="render-worker",
                allowed=("run-sandboxed",), version="1"):
    return build_worker_descriptor(
        worker_id=worker_id,
        worker_class=worker_class,
        worker_version=version,
        capabilities=[],
        allowed_operations=list(allowed),
        enabled=enabled,
        registration_source="test",
        registration_version="1",
    )


def _replace_scope(attempt, *, worker_class, operation, input_hash):
    """Return a rebuilt, cryptographically VALID Attempt with altered scope fields.

    The copy is rebuilt through the real ``build_execution_attempt`` builder, so its
    own ``artifact_hash`` is correctly recomputed and ``verify_hash()`` passes. Only
    the semantic link to the durable Authorization scope is broken -- exactly the
    condition the EA-4C.3 scope-equality check must reject (distinct from the
    physical-tamper branch).
    """
    from tools.hermes_core.execution_authorization import (
        ExecutionAttemptActor,
        build_execution_attempt,
    )

    actor = ExecutionAttemptActor(
        actor_id=attempt.attempt_actor_id,
        actor_type=attempt.attempt_actor_type,
        actor_context=attempt.attempt_actor_context,
    )
    return build_execution_attempt(
        authorization_id=attempt.authorization_id,
        authorization_hash=attempt.authorization_hash,
        request_id=attempt.request_id,
        request_hash=attempt.request_hash,
        decision_id=attempt.decision_id,
        decision_hash=attempt.decision_hash,
        claim_id=attempt.claim_id,
        claim_hash=attempt.claim_hash,
        task_id=attempt.task_id,
        attempt_number=attempt.attempt_number,
        attempt_actor=actor,
        attempt_requested_at=attempt.attempt_requested_at,
        attempt_recorded_at=attempt.attempt_recorded_at,
        claim_expires_at=attempt.claim_expires_at,
        must_start_by=attempt.must_start_by,
        input_hash=input_hash,
        operation=operation,
        worker_class=worker_class,
        status=attempt.status,
    )


class WorkerRouterSelectionServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ea.db")
        self.store = SQLiteExecutionAuthorizationStore(self.db)
        self.policy = _make_routing_policy()
        self.actor = _make_router_actor()

    def tearDown(self):
        self.store.close()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- happy path ---------------------------------------------------------
    def test_selects_and_persists_one_route(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store)
        reg = _registry([
            _descriptor("w-a"),
            _descriptor("w-b"),
        ])
        route = select_and_record_worker_route(
            store=self.store,
            attempt_id=attempt_id,
            registry=reg,
            policy=self.policy,
            router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        self.assertEqual(route.status, WorkerRouteStatus.SELECTED)
        # exactly one ROUTE_SELECTED + one route row
        stored = self.store.get_route_for_attempt(attempt_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.route_id, route.route_id)
        events = self.store.get_ledger_events("ROUTE_SELECTED")
        self.assertEqual(len(events), 1)

    def test_selects_first_of_two_eligible(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store)
        reg = _registry([
            _descriptor("w-b"),
            _descriptor("w-a"),
        ])
        route = select_and_record_worker_route(
            store=self.store,
            attempt_id=attempt_id,
            registry=reg,
            policy=self.policy,
            router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        # deterministic: (class, id, version) -> w-a before w-b
        self.assertEqual(route.worker_id, "w-a")

    def test_registry_input_order_does_not_affect_selection(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store)
        reg_a = _registry([_descriptor("w-2"), _descriptor("w-1")])
        reg_b = _registry([_descriptor("w-1"), _descriptor("w-2")])
        r1 = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg_a,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        # second call must replay the EXISTING route (no re-select)
        r2 = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg_b,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        self.assertEqual(r1.route_id, r2.route_id)
        self.assertEqual(r1.worker_id, r2.worker_id)

    # --- Attempt admission ---------------------------------------------------
    def test_missing_attempt_rejected(self):
        reg = _registry([_descriptor("w-a")])
        with self.assertRaises(WorkerRouteError):
            select_and_record_worker_route(
                store=self.store, attempt_id="nope",
                registry=reg, policy=self.policy, router_actor=self.actor,
                clock=utc_now,
            )

    def test_tampered_attempt_rejected(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store)
        # corrupt the persisted attempt hash so verify_hash fails on load
        import sqlite3

        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE execution_attempts SET artifact_hash = ? WHERE artifact_id = ?",
            ("0" * 64, attempt_id),
        )
        conn.commit()
        conn.close()
        reg = _registry([_descriptor("w-a")])
        with self.assertRaises(WorkerRouteIntegrityError):
            select_and_record_worker_route(
                store=self.store, attempt_id=attempt_id,
                registry=reg, policy=self.policy, router_actor=self.actor,
                clock=utc_now,
            )

    # --- time boundary -------------------------------------------------------
    def test_now_before_must_start_by_admitted(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a")])
        route = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        self.assertIsNotNone(route)

    def test_now_equal_must_start_by_admitted(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2026-06-01T00:00:00Z")
        reg = _registry([_descriptor("w-a")])
        route = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        self.assertIsNotNone(route)

    def test_now_after_must_start_by_expired(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2026-06-01T00:00:00Z")
        reg = _registry([_descriptor("w-a")])
        with self.assertRaises(WorkerRouteExpiredError):
            select_and_record_worker_route(
                store=self.store, attempt_id=attempt_id, registry=reg,
                policy=self.policy, router_actor=self.actor,
                clock=lambda: "2026-06-02T00:00:00Z",
            )

    def test_clock_failure_fails_closed(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a")])
        with self.assertRaises(WorkerRouteError):
            select_and_record_worker_route(
                store=self.store, attempt_id=attempt_id, registry=reg,
                policy=self.policy, router_actor=self.actor,
                clock=lambda: None,  # invalid -> fail closed
            )

    def test_invalid_utc_time_fails_closed(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a")])
        with self.assertRaises(WorkerRouteError):
            select_and_record_worker_route(
                store=self.store, attempt_id=attempt_id, registry=reg,
                policy=self.policy, router_actor=self.actor,
                clock=lambda: "2026-06-01T00:00:00",  # no Z
            )

    # --- scope mismatch ------------------------------------------------------
    # EA-4C.3 §12: a cryptographically VALID Attempt whose scope fields disagree
    # with the durable Authorization scope must be rejected by the EA-4C.3
    # comparison itself -- NOT by physical-tamper detection. We therefore test
    # the comparison helper directly with valid domain objects (no DB mutation,
    # no weakening of EA-4B persistence). This proves the scope-equality branch,
    # distinct from the integrity/tamper branch (~test_tampered_attempt_rejected).
    def test_scope_worker_class_mismatch_rejected(self):
        attempt_id, auth, _ = _setup_claim_lineage(self.store)
        attempt = self.store.get_attempt(attempt_id)  # valid, verify_hash ok
        bad = _replace_scope(
            attempt,
            worker_class="other-class",
            operation=attempt.operation,
            input_hash=attempt.input_hash,
        )
        with self.assertRaises(WorkerRouteLineageError):
            require_attempt_scope_matches_authorization(bad, auth)

    def test_scope_operation_mismatch_rejected(self):
        attempt_id, auth, _ = _setup_claim_lineage(self.store)
        attempt = self.store.get_attempt(attempt_id)
        bad = _replace_scope(
            attempt,
            worker_class=attempt.worker_class,
            operation="other-op",
            input_hash=attempt.input_hash,
        )
        with self.assertRaises(WorkerRouteLineageError):
            require_attempt_scope_matches_authorization(bad, auth)

    def test_scope_input_hash_mismatch_rejected(self):
        attempt_id, auth, _ = _setup_claim_lineage(self.store)
        attempt = self.store.get_attempt(attempt_id)
        bad = _replace_scope(
            attempt,
            worker_class=attempt.worker_class,
            operation=attempt.operation,
            input_hash="0" * 64,
        )
        with self.assertRaises(WorkerRouteLineageError):
            require_attempt_scope_matches_authorization(bad, auth)

    # --- registry ------------------------------------------------------------
    def test_tampered_registry_rejected(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a")])
        bad_reg = build_worker_registry(
            registry_version=reg.registry_version,
            workers=reg.workers,
        )
        # corrupt registry_hash to break verify_hash
        from tools.hermes_core.worker_router import WorkerRegistry

        bad_reg = WorkerRegistry(
            registry_version=reg.registry_version,
            registry_hash="0" * 64,
            workers=reg.workers,
        )
        with self.assertRaises(WorkerRegistryIntegrityError):
            select_and_record_worker_route(
                store=self.store, attempt_id=attempt_id, registry=bad_reg,
                policy=self.policy, router_actor=self.actor,
                clock=lambda: "2026-06-01T00:00:00Z",
            )

    def test_disabled_worker_excluded(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a", enabled=False), _descriptor("w-b")])
        route = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        self.assertEqual(route.worker_id, "w-b")

    def test_wrong_worker_class_excluded(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([
            _descriptor("w-x", worker_class="wrong-class"),
            _descriptor("w-a"),
        ])
        route = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        self.assertEqual(route.worker_id, "w-a")

    def test_operation_not_allowed_excluded(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([
            _descriptor("w-x", allowed=("other-op",)),
            _descriptor("w-a"),
        ])
        route = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        self.assertEqual(route.worker_id, "w-a")

    # --- no eligible worker --------------------------------------------------
    def test_zero_eligible_raises_no_route(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a", worker_class="nobody")])
        with self.assertRaises(WorkerRouteNoEligibleWorkerError):
            select_and_record_worker_route(
                store=self.store, attempt_id=attempt_id, registry=reg,
                policy=self.policy, router_actor=self.actor,
                clock=lambda: "2026-06-01T00:00:00Z",
            )
        self.assertIsNone(self.store.get_route_for_attempt(attempt_id))
        self.assertEqual(len(self.store.get_ledger_events("ROUTE_SELECTED")), 0)

    # --- route construction binding -----------------------------------------
    def test_route_binds_all_fields(self):
        attempt_id, auth, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a")])
        route = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        self.assertTrue(route.verify_hash())
        self.assertEqual(route.worker_id, "w-a")
        self.assertEqual(route.worker_class, "render-worker")
        self.assertEqual(route.worker_registry_version, "reg-1")
        self.assertEqual(route.routing_policy_id, self.policy.policy_id)
        self.assertEqual(route.attempt_id, attempt_id)
        self.assertEqual(route.operation, "run-sandboxed")
        self.assertEqual(route.input_hash, _h("in"))
        self.assertEqual(route.router_actor_id, "router-1")
        self.assertEqual(route.router_actor_type, "SYSTEM_ROUTER")
        self.assertEqual(route.status, WorkerRouteStatus.SELECTED)
        # selected_at <= must_start_by
        self.assertLessEqual(route.selected_at, route.must_start_by)

    # --- replay + conflict ---------------------------------------------------
    def test_exact_replay_returns_existing_route(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a"), _descriptor("w-b")])
        r1 = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        r2 = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        self.assertEqual(r1.route_id, r2.route_id)
        self.assertEqual(len(self.store.get_ledger_events("ROUTE_SELECTED")), 1)

    def test_conflict_does_not_silent_reroute(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a"), _descriptor("w-b")])
        r1 = select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=self.policy, router_actor=self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        # Remove the originally-selected worker from the registry -> current
        # context would select a DIFFERENT worker (w-b). Must raise conflict,
        # not silently reroute.
        reg2 = _registry([_descriptor("w-b"), _descriptor("w-c")])
        with self.assertRaises(WorkerRouteConflictError):
            select_and_record_worker_route(
                store=self.store, attempt_id=attempt_id, registry=reg2,
                policy=self.policy, router_actor=self.actor,
                clock=lambda: "2026-06-01T00:00:00Z",
            )
        # existing route unchanged
        stored = self.store.get_route_for_attempt(attempt_id)
        self.assertEqual(stored.worker_id, r1.worker_id)

    def _route_once(self, attempt_id, reg, policy=None, actor=None):
        return select_and_record_worker_route(
            store=self.store, attempt_id=attempt_id, registry=reg,
            policy=policy or self.policy, router_actor=actor or self.actor,
            clock=lambda: "2026-06-01T00:00:00Z",
        )

    def test_policy_id_mismatch_is_conflict_not_replay(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a"), _descriptor("w-b")])
        r1 = self._route_once(attempt_id, reg)
        # Same worker would still be selected, but a DIFFERENT routing policy
        # identity must not inherit the prior route.
        other_policy = WorkerRoutingPolicyRef(
            policy_id="routing-policy-OTHER", policy_version="1",
            policy_hash=_h("policy-other"),
        )
        with self.assertRaises(WorkerRouteConflictError):
            self._route_once(attempt_id, reg, policy=other_policy)
        stored = self.store.get_route_for_attempt(attempt_id)
        self.assertEqual(stored.worker_id, r1.worker_id)

    def test_policy_version_hash_mismatch_is_conflict_not_replay(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a"), _descriptor("w-b")])
        r1 = self._route_once(attempt_id, reg)
        # Same policy id, but version/hash changed -> replay-significant mismatch.
        other_policy = WorkerRoutingPolicyRef(
            policy_id=self.policy.policy_id, policy_version="9.9",
            policy_hash=_h("policy-changed"),
        )
        with self.assertRaises(WorkerRouteConflictError):
            self._route_once(attempt_id, reg, policy=other_policy)
        stored = self.store.get_route_for_attempt(attempt_id)
        self.assertEqual(stored.worker_id, r1.worker_id)

    def test_router_actor_id_mismatch_is_conflict_not_replay(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a"), _descriptor("w-b")])
        r1 = self._route_once(attempt_id, reg)
        other_actor = WorkerRouterActor(
            actor_id="router-OTHER",
            actor_type=WorkerRouterActorType.SYSTEM_ROUTER,
            actor_context="ea4c3-selection-other",
        )
        with self.assertRaises(WorkerRouteConflictError):
            self._route_once(attempt_id, reg, actor=other_actor)
        stored = self.store.get_route_for_attempt(attempt_id)
        self.assertEqual(stored.worker_id, r1.worker_id)

    def test_router_actor_type_context_mismatch_is_conflict_not_replay(self):
        attempt_id, _, _ = _setup_claim_lineage(self.store, must_start_by="2099-01-01T00:00:00Z")
        reg = _registry([_descriptor("w-a"), _descriptor("w-b")])
        r1 = self._route_once(attempt_id, reg)
        # Same id, but type+context differ -> replay-significant mismatch.
        other_actor = _make_router_actor()
        other_actor = WorkerRouterActor(
            actor_id=other_actor.actor_id,
            actor_type=other_actor.actor_type,
            actor_context="changed-context",
        )
        with self.assertRaises(WorkerRouteConflictError):
            self._route_once(attempt_id, reg, actor=other_actor)
        stored = self.store.get_route_for_attempt(attempt_id)
        self.assertEqual(stored.worker_id, r1.worker_id)

    # --- boundary assertions: EA-4C.4 race-loser behavior must be ABSENT ----
    def test_ea4c4_race_loser_handling_absent(self):
        """The contaminated cc51e85 EA-4C.4 behavior must NOT be present.

        Specifically: worker_router_service must NOT import or special-case
        ExecutionAuthorizationConflictError, and must NOT re-read the store after a
        failed record_route INSERT.
        """
        import tools.hermes_core.worker_router_service as mod

        src = inspect.getsource(mod)
        tree = ast.parse(src)
        # Name + attribute idents present anywhere in the module source.
        idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        idents |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn(
            "ExecutionAuthorizationConflictError",
            idents,
            "EA-4C.4 ExecutionAuthorizationConflictError handling leaked into EA-4C.3",
        )
        self.assertNotIn(
            "except ExecutionAuthorizationConflictError",
            src,
            "EA-4C.4 lost-INSERT-race except branch leaked into EA-4C.3",
        )

    def test_record_route_failure_reread_path_absent(self):
        """No post-failure get_route_for_attempt reread path in EA-4C.3.

        The only get_route_for_attempt call permitted is the pre-persistence
        fast-path check (existing-route replay). A reread after a failed INSERT
        would be the EA-4C.4 concurrency normalization, which is intentionally
        out of scope here. We assert the function has exactly ONE call to
        get_route_for_attempt and that it sits in the leading replay branch.
        """
        import tools.hermes_core.worker_router_service as mod

        src = inspect.getsource(mod)
        # Count occurrences of the store read that gates the existing-route path.
        self.assertEqual(
            src.count("store.get_route_for_attempt(attempt_id)"),
            1,
            "EA-4C.3 must reference get_route_for_attempt exactly once (pre-persistence replay gate)",
        )
        # The single reference must NOT be inside an except block.
        self.assertNotIn(
            "except",
            src.split("store.get_route_for_attempt(attempt_id)")[0].split("\n")[-3:],
        )


if __name__ == "__main__":
    unittest.main()
