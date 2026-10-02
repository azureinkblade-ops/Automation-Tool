"""EA-4C.4 focused concurrency tests (exactly-one route invariant under races).

Concurrency model: each racing participant operates through its OWN
``SQLiteExecutionAuthorizationStore`` instance pointed at the SAME db file.
This is the realistic multi-worker deployment (each worker/router process has
its own connection) and also avoids the single shared-connection thread-safety
constraint. The DB layer owns mutual exclusion via BEGIN IMMEDIATE +
UNIQUE(attempt_id); the service owns the loser-resolution semantics.

KEY CORRECTION vs the contaminated run: Races B/C/D begin from an UNROUTED
Attempt and race SIMULTANEOUSLY. They do not pre-create a route and then probe
a divergent context -- that would only prove EA-4C.3 replay conflict, not the
EA-4C.4 lost-INSERT-race normalization. Here every participant calls
``select_and_record_worker_route`` concurrently against the same fresh Attempt.

True Race B (the previously-missing proof):

    same unrouted Attempt
      Selector A registry: [w-a] -> selects w-a
      Selector B registry: [w-b] -> selects w-b
      both start concurrently
    -> whichever selector wins persists
    -> the other re-reads the winner and receives WorkerRouteConflictError
    -> exactly one route + exactly one ROUTE_SELECTED remain.
"""

import os
import tempfile
import threading
import unittest
from datetime import datetime
from hashlib import sha256

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
    WorkerRouteDecision,
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
    select_and_record_worker_route,
)


def _h(s):
    return sha256(s.encode("utf-8")).hexdigest()


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


def _setup_claim_lineage(store, task_id="task-1", scope=None, must_start_by=None,
                          consume_clock="2026-01-01T00:00:05Z"):
    """Build + persist a real Attempt (mirrors the EA-4C.3 test chain).

    ``must_start_by`` is controlled at attempt-construction time (consume clock +
    window), never by mutating a persisted row afterwards.
    """
    if scope is None:
        scope = _make_scope()
    if must_start_by is None:
        must_start_by = "2099-01-01T00:00:00Z"
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


class ConcurrencyHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ea4c4.sqlite")
        # ONE store builds the attempt chain (then closed); racers use their own.
        self.setup_store = SQLiteExecutionAuthorizationStore(self.db)
        self.attempt_id, self.auth, _ = _setup_claim_lineage(self.setup_store)
        self.setup_store.close()
        self.policy = _make_routing_policy()
        self.actor = _make_router_actor()
        self.clock = "2026-06-01T00:00:00Z"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _thread_store(self):
        """Each participant gets its own store connection to the SAME db file."""
        return SQLiteExecutionAuthorizationStore(self.db)

    def _assert_exactly_one(self):
        route = self._thread_store().get_route_for_attempt(self.attempt_id)
        events = self._thread_store().get_ledger_events("ROUTE_SELECTED")
        self.assertIsNotNone(route, "expected exactly one route, got none")
        self.assertEqual(len(events), 1, f"expected exactly one ROUTE_SELECTED, got {len(events)}")

    def _no_sqlite_leak(self, outcomes):
        import sqlite3

        for o in outcomes:
            if isinstance(o, Exception):
                self.assertNotIsInstance(
                    o, (sqlite3.OperationalError, sqlite3.IntegrityError, sqlite3.ProgrammingError),
                    f"raw sqlite error leaked: {type(o)}")
                self.assertNotIn("sqlite3", type(o).__module__,
                                 f"raw sqlite module leaked: {type(o)}")

    def _race_unrouted(self, n_threads, registry, policy=None, actor=None, clock=None):
        """Race N participants concurrently against the SAME (unrouted) Attempt.

        Each participant uses its own store connection. Returns the list of
        per-thread outcomes (WorkerRouteDecision or Exception), aligned by index.
        """
        policy = policy or self.policy
        actor = actor or self.actor
        clock = clock or self.clock
        outcomes = [None] * n_threads
        barrier = threading.Barrier(n_threads)

        def worker(idx):
            st = self._thread_store()
            barrier.wait()
            try:
                route = select_and_record_worker_route(
                    store=st, attempt_id=self.attempt_id, registry=registry,
                    policy=policy, router_actor=actor, clock=lambda: clock,
                )
                outcomes[idx] = route
            except Exception as exc:  # noqa: BLE001 - capture for assertion
                outcomes[idx] = exc

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        return outcomes


# --------------------------------------------------------------------------- #
# Races
# --------------------------------------------------------------------------- #

class WorkerRouterConcurrencyInvariantTests(ConcurrencyHarness):
    # --- Race A: identical context -----------------------------------------
    def test_race_identical_context(self):
        outcomes = self._race_unrouted(8, _registry([_descriptor("w-a"), _descriptor("w-b")]))
        self._assert_exactly_one()
        self._no_sqlite_leak(outcomes)
        # All returned decisions converge on the SAME persisted route.
        winners = [o for o in outcomes if isinstance(o, WorkerRouteDecision)]
        self.assertGreaterEqual(len(winners), 1)
        self.assertEqual(
            {w.route_id for w in winners},
            {self._thread_store().get_route_for_attempt(self.attempt_id).route_id})

    # --- Race B: TRUE different worker (concurrent, unrouted) --------------
    def test_race_true_different_worker(self):
        # Selector A would pick w-a; Selector B would pick w-b. Both race on the
        # same unrouted Attempt. Exactly one persists; the other conflicts.
        reg_a = _registry([_descriptor("w-a")])
        reg_b = _registry([_descriptor("w-b")])
        outcomes = [None] * 2
        barrier = threading.Barrier(2)

        def worker(which):
            st = self._thread_store()
            barrier.wait()
            try:
                route = select_and_record_worker_route(
                    store=st, attempt_id=self.attempt_id,
                    registry=reg_a if which == 0 else reg_b,
                    policy=self.policy, router_actor=self.actor,
                    clock=lambda: self.clock)
                outcomes[which] = route
            except Exception as exc:  # noqa
                outcomes[which] = exc

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self._assert_exactly_one()
        routes = [o for o in outcomes if isinstance(o, WorkerRouteDecision)]
        errors = [o for o in outcomes if isinstance(o, Exception)]
        # Exactly one winner persisted a route; the other lost the race and must
        # resolve to a typed WorkerRouteConflictError (not a sqlite leak).
        self.assertEqual(len(routes), 1, f"expected exactly one winner, got {len(routes)}")
        self.assertEqual(len(errors), 1, f"expected exactly one loser, got {len(errors)}")
        self.assertIsInstance(errors[0], WorkerRouteConflictError,
                              f"loser must conflict, got {type(errors[0]).__name__}: {errors[0]}")
        # The loser's conflict does not overwrite the winner's route.
        stored = self._thread_store().get_route_for_attempt(self.attempt_id)
        self.assertEqual(stored.worker_id, routes[0].worker_id)

    # --- Race C: simultaneous different policy (STARTS FROM UNROUTED Attempt)
    def test_race_simultaneous_different_policy(self):
        # Two selectors race SIMULTANEOUSLY against the SAME unrouted Attempt
        # (self.attempt_id is built fresh in setUp and has NO route). Both use
        # the same registry (both deterministically select w-a) but DIFFERENT
        # routing policies. Exactly one writer wins the record_route INSERT; the
        # loser re-reads the durable winner and, because its policy identity
        # (id/version/hash) differs, resolves to WorkerRouteConflictError.
        other_policy = WorkerRoutingPolicyRef(
            policy_id="routing-policy-OTHER", policy_version="1",
            policy_hash=_h("policy-other"))
        reg = _registry([_descriptor("w-a"), _descriptor("w-b")])
        out = [None] * 2
        barrier = threading.Barrier(2)

        def worker(which):
            st = self._thread_store()
            barrier.wait()
            try:
                r = select_and_record_worker_route(
                    store=st, attempt_id=self.attempt_id, registry=reg,
                    policy=self.policy if which == 0 else other_policy,
                    router_actor=self.actor, clock=lambda: self.clock)
                out[which] = r
            except Exception as exc:  # noqa: BLE001 - captured for assertion
                out[which] = exc

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=30)
        self._assert_exactly_one()
        routes = [o for o in out if isinstance(o, WorkerRouteDecision)]
        errs = [o for o in out if isinstance(o, Exception)]
        self.assertEqual(len(routes), 1, f"expected exactly one winner, got {len(routes)}")
        self.assertEqual(len(errs), 1, f"expected exactly one loser, got {len(errs)}")
        self.assertIsInstance(
            errs[0], WorkerRouteConflictError,
            f"divergent-policy loser must conflict, got {type(errs[0]).__name__}: {errs[0]}")

    # --- Race D: simultaneous different router actor (STARTS FROM UNROUTED Attempt)
    def test_race_simultaneous_different_router_actor(self):
        # Two selectors race SIMULTANEOUSLY against the SAME unrouted Attempt
        # (self.attempt_id has NO route). Both use the same registry (both
        # deterministically select w-a) but DIFFERENT router-actor identities.
        # Exactly one writer wins; the loser re-reads the durable winner and,
        # because its router-actor identity (id/type/context) differs, resolves
        # to WorkerRouteConflictError.
        other_actor = WorkerRouterActor(
            actor_id="router-OTHER",
            actor_type=WorkerRouterActorType.SYSTEM_ROUTER,
            actor_context="ea4c3-selection-other")
        reg = _registry([_descriptor("w-a"), _descriptor("w-b")])
        out = [None] * 2
        barrier = threading.Barrier(2)

        def make(which):
            def target():
                st = self._thread_store()
                barrier.wait()
                try:
                    r = select_and_record_worker_route(
                        store=st, attempt_id=self.attempt_id, registry=reg,
                        policy=self.policy,
                        router_actor=self.actor if which == 0 else other_actor,
                        clock=lambda: self.clock)
                    out[which] = r
                except Exception as exc:  # noqa: BLE001 - captured for assertion
                    out[which] = exc
            return target

        ts = [threading.Thread(target=make(i)) for i in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=30)
        self._assert_exactly_one()
        routes = [o for o in out if isinstance(o, WorkerRouteDecision)]
        errs = [o for o in out if isinstance(o, Exception)]
        self.assertEqual(len(routes), 1, f"expected exactly one winner, got {len(routes)}")
        self.assertEqual(len(errs), 1, f"expected exactly one loser, got {len(errs)}")
        self.assertIsInstance(
            errs[0], WorkerRouteConflictError,
            f"divergent-actor loser must conflict, got {type(errs[0]).__name__}: {errs[0]}")

    # --- Race E: registry reorder (benign drift) ---------------------------
    def test_race_registry_reorder(self):
        outcomes = self._race_unrouted(6, _registry([_descriptor("w-b"), _descriptor("w-a")]))
        self._assert_exactly_one()
        self._no_sqlite_leak(outcomes)
        winners = [o for o in outcomes if isinstance(o, WorkerRouteDecision)]
        self.assertEqual(
            {w.route_id for w in winners},
            {self._thread_store().get_route_for_attempt(self.attempt_id).route_id})

    # --- Race F: expired FRESH Attempt -------------------------------------
    def test_race_expired_fresh_attempt(self):
        # A fresh Attempt whose must_start_by is already in the past must raise
        # WorkerRouteExpiredError for EVERY racer; no route is created. Uses a
        # fresh db so the expired Attempt is independent of setUp's Attempt.
        import shutil

        fdb = os.path.join(self.tmp, "expired.sqlite")
        st = SQLiteExecutionAuthorizationStore(fdb)
        aid, _, _ = _setup_claim_lineage(st, must_start_by="2026-06-01T00:00:00Z")
        st.close()
        self.attempt_id = aid
        self.db = fdb
        outcomes = self._race_unrouted(6, _registry([_descriptor("w-a")]),
                                       clock="2026-06-02T00:00:00Z")
        for o in outcomes:
            self.assertIsInstance(o, WorkerRouteExpiredError,
                                  f"expected expired, got {type(o).__name__}: {o}")
        self.assertIsNone(self._thread_store().get_route_for_attempt(self.attempt_id))
        shutil.rmtree(os.path.dirname(fdb), ignore_errors=True)

    # --- Race F (boundary): inclusive boundary FRESH Attempt ---------------
    def test_race_inclusive_boundary_fresh_attempt(self):
        import shutil

        fdb = os.path.join(self.tmp, "boundary.sqlite")
        st = SQLiteExecutionAuthorizationStore(fdb)
        aid, _, _ = _setup_claim_lineage(st, must_start_by="2026-06-01T00:00:00Z")
        st.close()
        self.attempt_id = aid
        self.db = fdb
        outcomes = self._race_unrouted(6, _registry([_descriptor("w-a")]),
                                       clock="2026-06-01T00:00:00Z")
        winners = [o for o in outcomes if isinstance(o, WorkerRouteDecision)]
        self.assertGreaterEqual(len(winners), 1)
        self._assert_exactly_one()
        shutil.rmtree(os.path.dirname(fdb), ignore_errors=True)

    # --- Race G: zero eligible vs valid ------------------------------------
    def test_race_zero_eligible_vs_valid(self):
        reg_valid = _registry([_descriptor("w-a")])
        reg_empty = _registry([_descriptor("w-a", worker_class="nobody")])
        outcomes = [None] * 8
        barrier = threading.Barrier(8)

        def worker(idx):
            st = self._thread_store()
            reg = reg_empty if idx % 2 == 1 else reg_valid
            barrier.wait()
            try:
                r = select_and_record_worker_route(
                    store=st, attempt_id=self.attempt_id, registry=reg,
                    policy=self.policy, router_actor=self.actor,
                    clock=lambda: self.clock)
                outcomes[idx] = r
            except Exception as exc:  # noqa
                outcomes[idx] = exc

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self._assert_exactly_one()
        self._no_sqlite_leak(outcomes)
        for o in outcomes:
            if isinstance(o, Exception):
                self.assertIsInstance(
                    o, (WorkerRouteNoEligibleWorkerError, WorkerRouteDecision),
                    f"zero-eligible must raise typed error, got {type(o).__name__}: {o}")

    # --- Race H: replay wave ------------------------------------------------
    def test_race_replay_wave(self):
        # First concurrent wave routes once; the second concurrent wave replays.
        self._race_unrouted(4, _registry([_descriptor("w-a"), _descriptor("w-b")]))
        self._assert_exactly_one()
        outcomes = self._race_unrouted(4, _registry([_descriptor("w-a"), _descriptor("w-b")]))
        self._assert_exactly_one()
        self._no_sqlite_leak(outcomes)
        winners = [o for o in outcomes if isinstance(o, WorkerRouteDecision)]
        self.assertEqual(
            {w.route_id for w in winners},
            {self._thread_store().get_route_for_attempt(self.attempt_id).route_id})


# --------------------------------------------------------------------------- #
# Stress
# --------------------------------------------------------------------------- #

class WorkerRouterConcurrencyStressTests(ConcurrencyHarness):
    # --- Stress: identical participants (FRESH Attempts, repeatability) ----
    def test_stress_identical_fresh_attempts(self):
        # 25 independent fresh race instances; each instance uses its OWN db
        # file with a fresh unrouted Attempt, then runs 4 concurrent identical-
        # context participants (registry [w-a, w-b]). For every instance we
        # require: exactly one durable route, exactly one ROUTE_SELECTED, all 4
        # callers converge on the same route_id/hash, 0 raw sqlite errors, 0
        # unexpected outcomes. This establishes repeatability across fresh
        # Attempt/DB lifecycles (not just one giant wave). Total: 100 invocations.
        import shutil

        for inst in range(25):
            inst_db = os.path.join(self.tmp, f"id_{inst}.sqlite")
            st = SQLiteExecutionAuthorizationStore(inst_db)
            aid, _, _ = _setup_claim_lineage(st)
            st.close()
            reg = _registry([_descriptor("w-a"), _descriptor("w-b")])
            out = [None] * 4
            barrier = threading.Barrier(4)

            def worker(idx, aid=aid, reg=reg):
                s = SQLiteExecutionAuthorizationStore(inst_db)
                barrier.wait()
                try:
                    r = select_and_record_worker_route(
                        store=s, attempt_id=aid, registry=reg,
                        policy=self.policy, router_actor=self.actor,
                        clock=lambda: self.clock)
                    out[idx] = r
                except Exception as exc:  # noqa: BLE001 - captured for assertion
                    out[idx] = exc

            ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=30)
            # exactly one route + exactly one ROUTE_SELECTED
            rs = SQLiteExecutionAuthorizationStore(inst_db)
            route = rs.get_route_for_attempt(aid)
            events = rs.get_ledger_events("ROUTE_SELECTED")
            self.assertIsNotNone(route, f"instance {inst}: expected 1 route, got none")
            self.assertEqual(len(events), 1, f"instance {inst}: expected 1 ROUTE_SELECTED, got {len(events)}")
            # all 4 callers return the same route_id + hash
            winners = [o for o in out if isinstance(o, WorkerRouteDecision)]
            self.assertEqual(len(winners), 4, f"instance {inst}: expected 4 winners, got {len(winners)}")
            self.assertEqual(
                {w.route_id for w in winners}, {route.route_id},
                f"instance {inst}: callers diverged on route_id")
            self.assertEqual(
                {w.artifact_hash for w in winners}, {route.artifact_hash},
                f"instance {inst}: callers diverged on artifact_hash")
            # no raw sqlite leak + no unexpected outcomes
            import sqlite3

            for o in out:
                if isinstance(o, Exception):
                    self.assertNotIsInstance(
                        o, (sqlite3.OperationalError, sqlite3.IntegrityError, sqlite3.ProgrammingError),
                        f"instance {inst}: raw sqlite error leaked: {type(o)}")
                    self.assertNotIn("sqlite3", type(o).__module__,
                                     f"instance {inst}: raw sqlite module leaked: {type(o)}")
            rs.close()
            shutil.rmtree(os.path.dirname(inst_db), ignore_errors=True)

    # --- Stress: true different-worker -------------------------------------
    def test_stress_true_different_worker(self):
        # 40 fresh race instances; each instance uses its OWN db file (a fresh
        # Attempt cannot share an authorization/claim with the shared db), then
        # races A=[w-a] vs B=[w-b] concurrently against that unrouted Attempt.
        w_a_wins = 0
        w_b_wins = 0
        conflicts = 0
        unexpected = []
        import shutil

        for _ in range(40):
            inst_db = os.path.join(self.tmp, f"inst_{_}.sqlite")
            st = SQLiteExecutionAuthorizationStore(inst_db)
            aid, _, _ = _setup_claim_lineage(st)
            st.close()
            reg_a = _registry([_descriptor("w-a")])
            reg_b = _registry([_descriptor("w-b")])
            out = [None] * 2
            barrier = threading.Barrier(2)

            def worker(which, aid=aid, reg_a=reg_a, reg_b=reg_b):
                s = SQLiteExecutionAuthorizationStore(inst_db)
                barrier.wait()
                try:
                    r = select_and_record_worker_route(
                        store=s, attempt_id=aid,
                        registry=reg_a if which == 0 else reg_b,
                        policy=self.policy, router_actor=self.actor,
                        clock=lambda: self.clock)
                    out[which] = r
                except Exception as exc:  # noqa
                    out[which] = exc

            ts = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=30)
            routes = [o for o in out if isinstance(o, WorkerRouteDecision)]
            errs = [o for o in out if isinstance(o, Exception)]
            self.assertEqual(len(routes), 1, f"expected 1 winner, got {len(routes)}")
            self.assertEqual(len(errs), 1, f"expected 1 conflict loser, got {len(errs)}")
            self.assertIsInstance(errs[0], WorkerRouteConflictError,
                                  f"loser must conflict, got {type(errs[0]).__name__}")
            if routes[0].worker_id == "w-a":
                w_a_wins += 1
            elif routes[0].worker_id == "w-b":
                w_b_wins += 1
            conflicts += 1
            shutil.rmtree(os.path.dirname(inst_db), ignore_errors=True)
        self.assertEqual(w_a_wins + w_b_wins, 40)
        self.assertEqual(conflicts, 40)
        self.assertEqual(unexpected, [])

    # --- Stress: conflicting participants ----------------------------------
    def test_stress_conflicting(self):
        other_policy = WorkerRoutingPolicyRef(
            policy_id="routing-policy-OTHER", policy_version="1",
            policy_hash=_h("policy-other"))
        # Route once with base policy, then 40 divergent-policy threads race.
        select_and_record_worker_route(
            store=self._thread_store(), attempt_id=self.attempt_id,
            registry=_registry([_descriptor("w-a"), _descriptor("w-b")]),
            policy=self.policy, router_actor=self.actor, clock=lambda: self.clock)
        self._assert_exactly_one()
        outcomes = self._race_unrouted(40, _registry([_descriptor("w-a"), _descriptor("w-b")]),
                                       policy=other_policy)
        for o in outcomes:
            self.assertIsInstance(o, WorkerRouteConflictError,
                                  f"expected conflict, got {type(o).__name__}: {o}")
        self._assert_exactly_one()


if __name__ == "__main__":
    unittest.main()
