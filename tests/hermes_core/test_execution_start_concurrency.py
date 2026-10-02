"""EA-4D.2 focused tests: persistence + exclusive start admission.

Three layers (per the commit packet):
* test_execution_start_store     -- raw store reserve_start / replay / conflict / deadline / rollback
* test_execution_start_reservation -- service-layer reserve_execution_start (loads route, builds lineage)
* test_execution_start_concurrency -- concurrent start coordinators (exactly-one START_RESERVED)

Concurrency model mirrors EA-4C.4: each racer uses its OWN
``SQLiteExecutionStartStore`` pointed at the SAME db file (realistic
multi-coordinator deployment; avoids single shared-connection thread limits).
Mutual exclusion is owned by BEGIN IMMEDIATE + UNIQUE(route_id).

EA-4D.2 STOPS at START_RESERVED. No launch-attempt orchestration, no worker
invocation, no subprocess/network, no dispatch/enqueue, no EXECUTING transition.
"""

import os
import tempfile
import threading
import unittest
from datetime import datetime
from hashlib import sha256

from tools.hermes_core.execution_authorization import (
    ExecutionAttemptActor,
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
from tools.hermes_core.execution_start import (
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    ExecutionStartConflictError,
    ExecutionStartExpiredError,
    ExecutionStartIntegrityError,
    ExecutionStartLineageError,
    ExecutionStartReservation,
    build_execution_start_reservation,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_execution_start_store import (
    ExecutionStartLedgerEntry,
    SQLiteExecutionStartStore,
)
from tools.hermes_core.worker_router import (
    WorkerRouteConflictError,
    WorkerRouteDecision,
    WorkerRouteStatus,
    WorkerRouterActor,
    WorkerRouterActorType,
    WorkerRoutingPolicyRef,
    build_worker_descriptor,
    build_worker_registry,
    build_worker_route_decision,
)
from tools.hermes_core.execution_start_service import reserve_execution_start


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
        actor_id="issuer-1", actor_type=ExecutionAuthorizationActorType.SYSTEM,
        authority_role="grant", authentication_context=None)


def _make_policy():
    return ExecutionAuthorizationPolicyRef(policy_id="ea-baseline", policy_version="1.0")


def _make_routing_policy():
    return WorkerRoutingPolicyRef(
        policy_id="routing-policy-1", policy_version="1",
        policy_hash=_h("policy-1"))


def _make_launcher(actor_id="launcher-1", context="ea4d2"):
    return ExecutionLauncherActor(
        actor_id=actor_id, actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
        actor_context=context)


def _setup_claim_lineage(store, task_id="task-1", scope=None, must_start_by=None,
                         consume_clock="2026-01-01T00:00:05Z"):
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
        task_id=task_id, accepted_governance_artifact_id=acc_id,
        accepted_governance_hash=acc_hash, requested_scope=scope,
        requesting_actor=actor, authorization_policy=policy,
        requested_at="2026-01-01T00:00:00Z", request_reason="need exec")
    store.record_request(req)
    dec = build_execution_authorization_decision(
        request_id=req.request_id, request_hash=req.artifact_hash, task_id=task_id,
        decision_actor=actor, outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason="approved",
        authorization_id="execution-authorization-" + "d" * 16,
        authorization_policy=policy)
    auth = build_execution_authorization(
        task_id=task_id, accepted_governance_artifact_id=acc_id,
        accepted_governance_hash=acc_hash, request_id=req.request_id,
        request_hash=req.artifact_hash, decision_id=dec.decision_id,
        decision_hash=dec.artifact_hash, authorization_actor=actor,
        authorized_scope=scope, authorization_reason="operator approved",
        authorization_policy=policy, issued_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z", nonce="nonce-0001")
    dec2 = build_execution_authorization_decision(
        request_id=req.request_id, request_hash=req.artifact_hash, task_id=task_id,
        decision_actor=actor, outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason="approved", authorization_id=auth.authorization_id,
        authorization_policy=policy)
    store.record_granted_decision_and_authorization(dec2, auth)
    claim = build_execution_claim(
        authorization_id=auth.authorization_id, authorization_hash=auth.artifact_hash,
        request_id=auth.request_id, request_hash=auth.request_hash,
        decision_id=auth.decision_id, decision_hash=auth.decision_hash,
        task_id=auth.task_id,
        claimant=ExecutionClaimant(claimant_id="worker-manager",
                                   claimant_type="worker-manager",
                                   claimant_context="node-1"),
        claimed_at="2026-01-01T00:00:00Z", claim_expires_at="2099-01-01T00:00:00Z",
        authorization_policy=policy, claim_reason="claim by worker-manager")
    store.claim_authorization_atomically(auth.authorization_id, claim)
    result = _consume(store=store, authorization_id=auth.authorization_id,
                      claim_id=claim.claim_id, claimant=ExecutionAttemptActor(
                          actor_id="claimant-1", actor_type="SYSTEM",
                          actor_context=None),
                      must_start_within_seconds=window,
                      clock=lambda: consume_clock)
    return result.attempt_id, auth, must_start_by


def _record_route(store, attempt_id, worker_id="w-a", routing_policy=None,
                  router_actor=None, selected_at="2026-06-01T00:00:00Z",
                  worker_version="1"):
    if routing_policy is None:
        routing_policy = _make_routing_policy()
    if router_actor is None:
        router_actor = WorkerRouterActor(
            actor_id="router-1", actor_type=WorkerRouterActorType.SYSTEM_ROUTER,
            actor_context="ea4c3")
    attempt = store.get_attempt(attempt_id)
    registry = build_worker_registry(
        registry_version="reg-1",
        workers=[build_worker_descriptor(
            worker_id=worker_id, worker_class=attempt.worker_class,
            worker_version=worker_version, capabilities=[],
            allowed_operations=("run-sandboxed",),
            enabled=True, registration_source="test", registration_version="1")])
    route = build_worker_route_decision(
        attempt_id=attempt_id, attempt_hash=attempt.artifact_hash,
        authorization_id=attempt.authorization_id,
        authorization_hash=attempt.authorization_hash,
        claim_id=attempt.claim_id, claim_hash=attempt.claim_hash,
        request_id=attempt.request_id, request_hash=attempt.request_hash,
        decision_id=attempt.decision_id, decision_hash=attempt.decision_hash,
        task_id=attempt.task_id, worker_id=worker_id,
        worker_class=attempt.worker_class, registry=registry, policy=routing_policy,
        operation=attempt.operation, input_hash=attempt.input_hash,
        router_actor=router_actor, selected_at=selected_at,
        must_start_by=attempt.must_start_by)
    store.record_route(route)
    return route


# --------------------------------------------------------------------------- #
# Store-layer tests
# --------------------------------------------------------------------------- #


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ea4d2.sqlite")
        self.store = SQLiteExecutionStartStore(self.db)
        self.launcher = _make_launcher()

    def tearDown(self):
        self.store.close()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sample_reservation(self, route_id="route-1"):
        return build_execution_start_reservation(
            reservation_id=f"res-{route_id}",
            route_id=route_id, route_hash=_h(route_id),
            attempt_id="attempt-1", attempt_hash=_h("attempt"),
            authorization_id="auth-1", authorization_hash=_h("auth"),
            claim_id="claim-1", claim_hash=_h("claim"),
            request_id="req-1", request_hash=_h("req"),
            decision_id="dec-1", decision_hash=_h("dec"),
            task_id="task-1", worker_id="w-a", worker_class="render-worker",
            worker_version="1", operation="run-sandboxed", input_hash=_h("in"),
            reserved_at="2026-06-01T00:00:00Z",
            must_start_by="2099-01-01T00:00:00Z", launcher_actor=self.launcher)

    def test_reserve_persists_once(self):
        r = self._sample_reservation()
        out = self.store.reserve_start(r, now="2026-06-01T00:00:00Z",
                                       must_start_by="2099-01-01T00:00:00Z")
        self.assertEqual(out.status.value, "RESERVED")
        self.assertEqual(len(self.store.get_reservations_for_route("route-1")), 1)
        events = self.store.get_start_ledger_events("START_RESERVED")
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], ExecutionStartLedgerEntry)

    def test_exact_replay_returns_existing(self):
        r = self._sample_reservation()
        first = self.store.reserve_start(r, now="2026-06-01T00:00:00Z",
                                         must_start_by="2099-01-01T00:00:00Z")
        again = self.store.reserve_start(r, now="2026-06-01T00:00:00Z",
                                         must_start_by="2099-01-01T00:00:00Z")
        self.assertEqual(first.reservation_id, again.reservation_id)
        self.assertEqual(len(self.store.get_reservations_for_route("route-1")), 1)
        self.assertEqual(len(self.store.get_start_ledger_events("START_RESERVED")), 1)

    def test_different_launcher_conflict(self):
        r = self._sample_reservation()
        self.store.reserve_start(r, now="2026-06-01T00:00:00Z",
                                 must_start_by="2099-01-01T00:00:00Z")
        other = build_execution_start_reservation(
            reservation_id="res-route-1-b", route_id="route-1",
            route_hash=_h("route-1"), attempt_id="attempt-1",
            attempt_hash=_h("attempt"), authorization_id="auth-1",
            authorization_hash=_h("auth"), claim_id="claim-1", claim_hash=_h("claim"),
            request_id="req-1", request_hash=_h("req"), decision_id="dec-1",
            decision_hash=_h("dec"), task_id="task-1", worker_id="w-a",
            worker_class="render-worker", worker_version="1",
            operation="run-sandboxed", input_hash=_h("in"),
            reserved_at="2026-06-01T00:00:00Z", must_start_by="2099-01-01T00:00:00Z",
            launcher_actor=_make_launcher(actor_id="launcher-2"))
        with self.assertRaises(ExecutionStartConflictError):
            self.store.reserve_start(other, now="2026-06-01T00:00:00Z",
                                     must_start_by="2099-01-01T00:00:00Z")
        # Exactly one reservation remains; no silent transfer.
        self.assertEqual(len(self.store.get_reservations_for_route("route-1")), 1)

    def test_expired_deadline_fail_closed(self):
        # reserved_at == now, but must_start_by already passed relative to now.
        r = build_execution_start_reservation(
            reservation_id="res-route-1", route_id="route-1", route_hash=_h("route-1"),
            attempt_id="attempt-1", attempt_hash=_h("attempt"),
            authorization_id="auth-1", authorization_hash=_h("auth"),
            claim_id="claim-1", claim_hash=_h("claim"),
            request_id="req-1", request_hash=_h("req"),
            decision_id="dec-1", decision_hash=_h("dec"),
            task_id="task-1", worker_id="w-a", worker_class="render-worker",
            worker_version="1", operation="run-sandboxed", input_hash=_h("in"),
            reserved_at="2099-01-02T00:00:00Z", must_start_by="2099-01-01T00:00:00Z",
            launcher_actor=self.launcher)
        with self.assertRaises(ExecutionStartExpiredError):
            self.store.reserve_start(r, now="2099-01-02T00:00:00Z",
                                     must_start_by="2099-01-01T00:00:00Z")
        self.assertEqual(len(self.store.get_reservations_for_route("route-1")), 0)

    def test_inclusive_boundary_pass(self):
        r = build_execution_start_reservation(
            reservation_id="res-route-1", route_id="route-1", route_hash=_h("route-1"),
            attempt_id="attempt-1", attempt_hash=_h("attempt"),
            authorization_id="auth-1", authorization_hash=_h("auth"),
            claim_id="claim-1", claim_hash=_h("claim"),
            request_id="req-1", request_hash=_h("req"),
            decision_id="dec-1", decision_hash=_h("dec"),
            task_id="task-1", worker_id="w-a", worker_class="render-worker",
            worker_version="1", operation="run-sandboxed", input_hash=_h("in"),
            reserved_at="2099-01-01T00:00:00Z", must_start_by="2099-01-01T00:00:00Z",
            launcher_actor=self.launcher)
        out = self.store.reserve_start(r, now="2099-01-01T00:00:00Z",
                                       must_start_by="2099-01-01T00:00:00Z")
        self.assertEqual(out.status.value, "RESERVED")

    def test_rollback_seam_leaves_zero_residue(self):
        r = self._sample_reservation()
        self.store._fail_after_reservation_insert = True
        with self.assertRaises(Exception):
            self.store.reserve_start(r, now="2026-06-01T00:00:00Z",
                                     must_start_by="2099-01-01T00:00:00Z")
        self.assertEqual(len(self.store.get_reservations_for_route("route-1")), 0)
        self.assertEqual(len(self.store.get_start_ledger_events("START_RESERVED")), 0)

    def test_launch_attempt_table_empty(self):
        r = self._sample_reservation()
        self.store.reserve_start(r, now="2026-06-01T00:00:00Z",
                                 must_start_by="2099-01-01T00:00:00Z")
        # EA-4D.2 never writes a launch attempt; the table must stay empty.
        self.assertFalse(self.store.has_launch_attempt(r.reservation_id))

    # -- physical persisted tamper coverage (read-side fail-closed) ---------
    def _persist_sample(self):
        r = self._sample_reservation()
        self.store.reserve_start(r, now="2026-06-01T00:00:00Z",
                                 must_start_by="2099-01-01T00:00:00Z")
        return r

    def _tamper_column(self, column, bad_value):
        """Corrupt one physical column directly in the DB and assert read fails."""
        import sqlite3 as _sql

        conn = _sql.connect(self.db)
        conn.execute(
            f"UPDATE execution_start_reservations SET {column} = ? WHERE route_id = 'route-1'",
            (bad_value,))
        conn.commit()
        conn.close()

    def test_tamper_artifact_hash_fails_read(self):
        self._persist_sample()
        self._tamper_column("artifact_hash", "deadbeef")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_route_id_fails_read(self):
        r = self._persist_sample()
        self._tamper_column("route_id", "route-EVIL")
        # Read by the reservation's own id: the corrupted route binding must
        # fail closed on integrity verification (not silently disappear).
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservation(r.reservation_id)

    def test_tamper_route_hash_fails_read(self):
        self._persist_sample()
        self._tamper_column("route_hash", "deadbeef")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_attempt_id_fails_read(self):
        self._persist_sample()
        self._tamper_column("attempt_id", "attempt-EVIL")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_attempt_hash_fails_read(self):
        self._persist_sample()
        self._tamper_column("attempt_hash", "deadbeef")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_authorization_id_fails_read(self):
        self._persist_sample()
        self._tamper_column("authorization_id", "auth-EVIL")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_authorization_hash_fails_read(self):
        self._persist_sample()
        self._tamper_column("authorization_hash", "deadbeef")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_worker_id_fails_read(self):
        self._persist_sample()
        self._tamper_column("worker_id", "w-EVIL")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_worker_class_fails_read(self):
        self._persist_sample()
        self._tamper_column("worker_class", "evil-class")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_worker_version_fails_read(self):
        self._persist_sample()
        self._tamper_column("worker_version", "99")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_operation_fails_read(self):
        self._persist_sample()
        self._tamper_column("operation", "evil-op")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_input_hash_fails_read(self):
        self._persist_sample()
        self._tamper_column("input_hash", "deadbeef")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_launcher_actor_id_fails_read(self):
        self._persist_sample()
        self._tamper_column("launcher_actor_id", "evil-launcher")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_launcher_actor_type_fails_read(self):
        self._persist_sample()
        self._tamper_column("launcher_actor_type", "SYSTEM")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_launcher_actor_context_fails_read(self):
        self._persist_sample()
        self._tamper_column("launcher_actor_context", "evil-ctx")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_reserved_at_fails_read(self):
        self._persist_sample()
        self._tamper_column("reserved_at", "1999-01-01T00:00:00Z")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_must_start_by_fails_read(self):
        self._persist_sample()
        self._tamper_column("must_start_by", "1999-01-01T00:00:00Z")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")

    def test_tamper_status_fails_read(self):
        self._persist_sample()
        self._tamper_column("status", "STARTED")
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store.get_reservations_for_route("route-1")


# --------------------------------------------------------------------------- #
# Service-layer tests (load route via EA-4C store, build lineage)
# --------------------------------------------------------------------------- #


class ReservationServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.auth_db = os.path.join(self.tmp, "ea.sqlite")
        self.start_db = os.path.join(self.tmp, "ea4d2.sqlite")
        self.auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        self.attempt_id, _auth, _msb = _setup_claim_lineage(self.auth_store)
        self.route = _record_route(self.auth_store, self.attempt_id)
        self.auth_store.close()
        self.start_store = SQLiteExecutionStartStore(self.start_db)
        self.launcher = _make_launcher()

    def tearDown(self):
        self.start_store.close()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reserve_through_service(self):
        # Reopen authoritative store for the service read.
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        out = reserve_execution_start(
            store=auth_store, start_store=self.start_store,
            attempt_id=self.attempt_id, launcher_actor=self.launcher,
            clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()
        self.assertEqual(out.status.value, "RESERVED")
        self.assertEqual(out.route_id, self.route.route_id)
        self.assertEqual(out.worker_id, self.route.worker_id)
        self.assertEqual(len(self.start_store.get_reservations_for_route(self.route.route_id)), 1)
        self.assertEqual(len(self.start_store.get_start_ledger_events("START_RESERVED")), 1)

    def test_verified_registry_preserves_exact_worker_version(self):
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        attempt_id, _auth, _msb = _setup_claim_lineage(
            auth_store, task_id="task-version-1-0")
        route = _record_route(
            auth_store,
            attempt_id,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
        )
        attempt = auth_store.get_attempt(attempt_id)
        registry = build_worker_registry(
            registry_version=route.worker_registry_version,
            workers=[build_worker_descriptor(
                worker_id=route.worker_id,
                worker_class=attempt.worker_class,
                worker_version="1.0",
                capabilities=[],
                allowed_operations=["run-sandboxed"],
                enabled=True,
                registration_source="test",
                registration_version="1",
            )],
        )
        self.assertEqual(registry.registry_hash, route.worker_registry_hash)
        out = reserve_execution_start(
            store=auth_store,
            start_store=self.start_store,
            attempt_id=attempt_id,
            launcher_actor=self.launcher,
            worker_registry=registry,
            clock=lambda: "2026-06-01T00:00:00Z",
        )
        auth_store.close()
        self.assertEqual(out.worker_version, "1.0")

    def test_service_rejects_non_launcher(self):
        from tools.hermes_core.execution_start import ExecutionLauncherActor

        class _BadActorType:
            value = "SYSTEM"
        bad = ExecutionLauncherActor(
            actor_id="x", actor_type=_BadActorType(), actor_context=None)
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(Exception):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=bad,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_service_no_route_fail_closed(self):
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        # Attempt exists but has no route: must not reserve.
        new_attempt_id, _a, _m = _setup_claim_lineage(
            auth_store, task_id="task-2", must_start_by="2099-01-01T00:00:00Z")
        with self.assertRaises(Exception):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=new_attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    # -- authorization/attempt source binding (Section 23) ------------------
    def test_reservation_binds_durable_authorization_and_attempt(self):
        from tools.hermes_core.execution_authorization import (
            ExecutionAuthorization,
        )
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        out = reserve_execution_start(
            store=auth_store, start_store=self.start_store,
            attempt_id=self.attempt_id, launcher_actor=self.launcher,
            clock=lambda: "2026-06-01T00:00:00Z")
        attempt = auth_store.get_attempt(self.attempt_id)
        authorization = auth_store.get_authorization(attempt.authorization_id)
        # The reservation must derive hashes from the DURABLE artifacts, not
        # from the Route's copied downstream fields.
        self.assertEqual(out.authorization_hash, authorization.artifact_hash)
        self.assertEqual(out.attempt_hash, attempt.artifact_hash)
        self.assertNotEqual(out.authorization_hash, "EVIL")
        auth_store.close()

    # -- Route source: tampered artifact hash cannot acquire START_RESERVED --
    def test_route_tampered_hash_rejected(self):
        # Rebuild the persisted route's canonical payload with a wrong
        # artifact_hash so verify_hash() fails, but keep it otherwise present.
        import json
        import sqlite3 as _sql
        from tools.hermes_core.sqlite_execution_authorization_store import (
            _hash_route_linkage,
        )

        conn = _sql.connect(self.auth_db)
        conn.row_factory = _sql.Row
        cols = (
            "artifact_id, artifact_version, attempt_id, attempt_hash, "
            "authorization_id, authorization_hash, claim_id, claim_hash, "
            "request_id, request_hash, decision_id, decision_hash, task_id, "
            "worker_id, worker_class, worker_registry_version, "
            "worker_registry_hash, routing_policy_id, routing_policy_version, "
            "routing_policy_hash, router_actor_id, router_actor_type, "
            "router_actor_context, selected_at, must_start_by, operation, "
            "input_hash, status, canonical_payload"
        )
        row = conn.execute(
            f"SELECT {cols} FROM worker_routes WHERE attempt_id = ?",
            (self.attempt_id,)).fetchone()
        payload = json.loads(row["canonical_payload"])
        payload["artifact_hash"] = "0" * 64  # broken hash, valid JSON
        # Recompute the physical envelope from the (now broken) hash so the
        # store load passes its envelope check and the service reaches the
        # authoritative route.verify_hash() failure.
        linkage = _hash_route_linkage(
            row["artifact_id"], row["artifact_version"], "0" * 64,
            row["attempt_id"], row["attempt_hash"], row["authorization_id"],
            row["authorization_hash"], row["claim_id"], row["claim_hash"],
            row["request_id"], row["request_hash"], row["decision_id"],
            row["decision_hash"], row["task_id"], row["worker_id"],
            row["worker_class"], row["worker_registry_version"],
            row["worker_registry_hash"], row["routing_policy_id"],
            row["routing_policy_version"], row["routing_policy_hash"],
            row["router_actor_id"], row["router_actor_type"],
            row["router_actor_context"], row["selected_at"], row["must_start_by"],
            row["operation"], row["input_hash"], row["status"])
        conn.execute(
            "UPDATE worker_routes SET canonical_payload = ?, artifact_hash = ?, "
            "route_linkage_sha256 = ? WHERE artifact_id = ?",
            (json.dumps(payload), "0" * 64, linkage, row["artifact_id"]))
        conn.commit(); conn.close()
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartIntegrityError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        # No reservation / no START_RESERVED event may be created.
        self.assertEqual(
            len(self.start_store.get_reservations_for_route(self.route.route_id)), 0)
        self.assertEqual(
            len(self.start_store.get_start_ledger_events("START_RESERVED")), 0)
        auth_store.close()

    # -- Route source: non-SELECTED route rejected --------------------------
    def test_route_non_selected_rejected(self):
        import sqlite3 as _sql
        conn = _sql.connect(self.auth_db)
        conn.execute(
            "UPDATE worker_routes SET status = 'BUILDING' WHERE attempt_id = ?",
            (self.attempt_id,))
        conn.commit(); conn.close()
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartIntegrityError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    # -- semantic lineage mismatch via cryptographically VALID artifacts ----
    def _persist_route_with(self, **overrides):
        """Persist a rebuilt, hash-valid Route whose lineage fields are
        overridden (Section 21: valid artifact, wrong binding).

        Recomputes the canonical artifact_hash AND the physical
        route_linkage_sha256 envelope so the artifact still verifies on load;
        only the semantic lineage binding is changed (proving the EA-4D.2
        lineage comparison, not mere physical-tamper detection).
        """
        import json
        import sqlite3 as _sql
        from tools.hermes_core.hashing import sha256_payload
        from tools.hermes_core.sqlite_execution_authorization_store import (
            _hash_route_linkage,
        )

        conn = _sql.connect(self.auth_db)
        conn.row_factory = _sql.Row
        cols = (
            "artifact_id, artifact_version, artifact_hash, attempt_id, "
            "attempt_hash, authorization_id, authorization_hash, claim_id, "
            "claim_hash, request_id, request_hash, decision_id, decision_hash, "
            "task_id, worker_id, worker_class, worker_registry_version, "
            "worker_registry_hash, routing_policy_id, routing_policy_version, "
            "routing_policy_hash, router_actor_id, router_actor_type, "
            "router_actor_context, selected_at, must_start_by, operation, "
            "input_hash, status, canonical_payload"
        )
        row = conn.execute(
            f"SELECT {cols} FROM worker_routes WHERE attempt_id = ?",
            (self.attempt_id,)).fetchone()
        payload = json.loads(row["canonical_payload"])
        phys = {k: row[k] for k in (
            "artifact_id", "artifact_version", "attempt_id", "attempt_hash",
            "authorization_id", "authorization_hash", "claim_id", "claim_hash",
            "request_id", "request_hash", "decision_id", "decision_hash",
            "task_id", "worker_id", "worker_class", "worker_registry_version",
            "worker_registry_hash", "routing_policy_id", "routing_policy_version",
            "routing_policy_hash", "router_actor_id", "router_actor_type",
            "router_actor_context", "selected_at", "must_start_by", "operation",
            "input_hash", "status")}
        for k, v in overrides.items():
            payload[k] = v
            if k in phys:
                phys[k] = v
        new_hash = sha256_payload(payload)
        phys["artifact_hash"] = new_hash
        linkage = _hash_route_linkage(
            phys["artifact_id"], phys["artifact_version"], phys["artifact_hash"],
            phys["attempt_id"], phys["attempt_hash"], phys["authorization_id"],
            phys["authorization_hash"], phys["claim_id"], phys["claim_hash"],
            phys["request_id"], phys["request_hash"], phys["decision_id"],
            phys["decision_hash"], phys["task_id"], phys["worker_id"],
            phys["worker_class"], phys["worker_registry_version"],
            phys["worker_registry_hash"], phys["routing_policy_id"],
            phys["routing_policy_version"], phys["routing_policy_hash"],
            phys["router_actor_id"], phys["router_actor_type"],
            phys["router_actor_context"], phys["selected_at"], phys["must_start_by"],
            phys["operation"], phys["input_hash"], phys["status"])
        # Write back the overridden physical columns too, so the envelope
        # recomputation on load matches what we persisted here.
        sets = ["canonical_payload = ?", "artifact_hash = ?", "route_linkage_sha256 = ?"]
        params = [json.dumps(payload), new_hash, linkage]
        for k, v in overrides.items():
            if k in phys:
                sets.append(f"{k} = ?")
                params.append(v)
        params.append(row["artifact_id"])
        conn.execute(
            f"UPDATE worker_routes SET {', '.join(sets)} WHERE artifact_id = ?",
            params)
        conn.commit(); conn.close()

    def test_route_attempt_hash_mismatch_rejected(self):
        self._persist_route_with(attempt_hash="0" * 64)
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_route_claim_mismatch_rejected(self):
        self._persist_route_with(claim_id="claim-EVIL", claim_hash="0" * 64)
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_route_request_mismatch_rejected(self):
        self._persist_route_with(request_id="req-EVIL", request_hash="0" * 64)
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_route_decision_mismatch_rejected(self):
        self._persist_route_with(decision_id="dec-EVIL", decision_hash="0" * 64)
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_route_task_mismatch_rejected(self):
        self._persist_route_with(task_id="task-EVIL")
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_route_operation_mismatch_rejected(self):
        self._persist_route_with(operation="evil-op")
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_route_input_hash_mismatch_rejected(self):
        self._persist_route_with(input_hash="0" * 64)
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_route_worker_class_mismatch_rejected(self):
        self._persist_route_with(worker_class="evil-class")
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_route_authorization_binding_mismatch_rejected(self):
        self._persist_route_with(
            authorization_id="auth-EVIL", authorization_hash="0" * 64)
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_attempt_authorization_binding_mismatch_rejected(self):
        # Build a cryptographically-valid rebuilt Attempt whose authorization
        # binding differs from the durable Authorization (valid artifact, wrong
        # binding) — proving semantic lineage validation, not physical tamper.
        import json
        import sqlite3 as _sql
        from tools.hermes_core.hashing import sha256_payload
        from tools.hermes_core.sqlite_execution_authorization_store import (
            _hash_attempt_linkage,
        )

        conn = _sql.connect(self.auth_db)
        conn.row_factory = _sql.Row
        cols = (
            "artifact_id, authorization_id, authorization_hash, request_id, "
            "request_hash, decision_id, decision_hash, claim_id, claim_hash, "
            "task_id, attempt_number, attempt_actor_id, attempt_actor_type, "
            "attempt_actor_context, attempt_requested_at, attempt_recorded_at, "
            "claim_expires_at, must_start_by, input_hash, operation, "
            "worker_class, status, canonical_payload"
        )
        row = conn.execute(
            f"SELECT {cols} FROM execution_attempts WHERE artifact_id = ?",
            (self.attempt_id,)).fetchone()
        payload = json.loads(row["canonical_payload"])
        phys = {k: row[k] for k in (
            "artifact_id", "authorization_id", "authorization_hash", "request_id",
            "request_hash", "decision_id", "decision_hash", "claim_id",
            "claim_hash", "task_id", "attempt_number", "attempt_actor_id",
            "attempt_actor_type", "attempt_actor_context", "attempt_requested_at",
            "attempt_recorded_at", "claim_expires_at", "must_start_by",
            "input_hash", "operation", "worker_class", "status")}
        payload["authorization_id"] = "auth-EVIL"
        payload["authorization_hash"] = "0" * 64
        phys["authorization_id"] = "auth-EVIL"
        phys["authorization_hash"] = "0" * 64
        new_hash = sha256_payload(payload)
        phys["artifact_hash"] = new_hash
        linkage = _hash_attempt_linkage(
            phys["artifact_id"], phys["authorization_id"], phys["authorization_hash"],
            phys["request_id"], phys["request_hash"], phys["decision_id"],
            phys["decision_hash"], phys["claim_id"], phys["claim_hash"],
            phys["task_id"], phys["attempt_number"], phys["attempt_actor_id"],
            phys["attempt_actor_type"], phys["attempt_actor_context"],
            phys["attempt_requested_at"], phys["attempt_recorded_at"],
            phys["claim_expires_at"], phys["must_start_by"], phys["input_hash"],
            phys["operation"], phys["worker_class"], phys["status"])
        conn.execute(
            "UPDATE execution_attempts SET canonical_payload = ?, artifact_hash = ?, "
            "authorization_id = ?, authorization_hash = ?, attempt_linkage_sha256 = ? "
            "WHERE artifact_id = ?",
            (json.dumps(payload), new_hash, phys["authorization_id"],
             phys["authorization_hash"], linkage, self.attempt_id))
        conn.commit(); conn.close()
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_route_attempt_must_start_by_mismatch_rejected(self):
        self._persist_route_with(must_start_by="1999-01-01T00:00:00Z")
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartLineageError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00Z")
        auth_store.close()

    # -- clock discipline (Section 22) ---------------------------------------
    def test_clock_valid_utc_accepted(self):
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        out = reserve_execution_start(
            store=auth_store, start_store=self.start_store,
            attempt_id=self.attempt_id, launcher_actor=self.launcher,
            clock=lambda: "2026-06-01T00:00:00Z")
        self.assertEqual(out.reserved_at, "2026-06-01T00:00:00Z")
        auth_store.close()

    def test_clock_called_once(self):
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        calls = {"n": 0}

        def _clock():
            calls["n"] += 1
            return "2026-06-01T00:00:00Z"

        reserve_execution_start(
            store=auth_store, start_store=self.start_store,
            attempt_id=self.attempt_id, launcher_actor=self.launcher, clock=_clock)
        self.assertEqual(calls["n"], 1)
        auth_store.close()

    def test_clock_malformed_rejected(self):
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartIntegrityError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "not-a-timestamp")
        auth_store.close()

    def test_clock_non_utc_rejected(self):
        auth_store = SQLiteExecutionAuthorizationStore(self.auth_db)
        with self.assertRaises(ExecutionStartIntegrityError):
            reserve_execution_start(
                store=auth_store, start_store=self.start_store,
                attempt_id=self.attempt_id, launcher_actor=self.launcher,
                clock=lambda: "2026-06-01T00:00:00")  # no trailing Z
        auth_store.close()

    # -- low-level store deadline/reserved_at consistency (Section 15) ------
    def test_store_reserved_at_mismatch_rejected(self):
        r = build_execution_start_reservation(
            reservation_id="res-route-1", route_id="route-1", route_hash=_h("route-1"),
            attempt_id="attempt-1", attempt_hash=_h("attempt"),
            authorization_id="auth-1", authorization_hash=_h("auth"),
            claim_id="claim-1", claim_hash=_h("claim"),
            request_id="req-1", request_hash=_h("req"),
            decision_id="dec-1", decision_hash=_h("dec"),
            task_id="task-1", worker_id="w-a", worker_class="render-worker",
            worker_version="1", operation="run-sandboxed", input_hash=_h("in"),
            reserved_at="2026-06-01T00:00:00Z", must_start_by="2099-01-01T00:00:00Z",
            launcher_actor=self.launcher)
        # reserved_at in artifact differs from store 'now' -> low-level reject.
        with self.assertRaises(ExecutionStartIntegrityError):
            self.store_test().reserve_start(
                r, now="2026-06-02T00:00:00Z", must_start_by="2099-01-01T00:00:00Z")

    def store_test(self):
        st = SQLiteExecutionStartStore(self._tmp_start_db())
        return st

    def _tmp_start_db(self):
        import tempfile
        import os as _os
        d = tempfile.mkdtemp()
        return _os.path.join(d, "lowlevel.sqlite")


# --------------------------------------------------------------------------- #
# Concurrency tests (exactly-one START_RESERVED under races)
# --------------------------------------------------------------------------- #


class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.auth_db = os.path.join(self.tmp, "ea.sqlite")
        self.start_db = os.path.join(self.tmp, "ea4d2.sqlite")
        self.setup_auth = SQLiteExecutionAuthorizationStore(self.auth_db)
        self.attempt_id, _auth, _msb = _setup_claim_lineage(self.setup_auth)
        self.route = _record_route(self.setup_auth, self.attempt_id)
        self.setup_auth.close()
        self.launcher = _make_launcher()
        self.clock = "2026-06-01T00:00:00Z"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _thread_start_store(self):
        return SQLiteExecutionStartStore(self.start_db)

    def _auth_store(self):
        return SQLiteExecutionAuthorizationStore(self.auth_db)

    def _assert_exactly_one(self):
        st = self._thread_start_store()
        res = st.get_reservations_for_route(self.route.route_id)
        events = st.get_start_ledger_events("START_RESERVED")
        self.assertEqual(len(res), 1, f"expected exactly one reservation, got {len(res)}")
        self.assertEqual(len(events), 1, f"expected exactly one START_RESERVED, got {len(events)}")
        st.close()

    def _no_sqlite_leak(self, outcomes):
        import sqlite3

        for o in outcomes:
            if isinstance(o, Exception):
                self.assertNotIsInstance(
                    o, (sqlite3.OperationalError, sqlite3.IntegrityError,
                        sqlite3.ProgrammingError),
                    f"raw sqlite error leaked: {type(o)}")

    def _race(self, n_threads, launcher_for_idx=lambda i: _make_launcher()):
        """Race N coordinators concurrently against the SAME (routed) Attempt.

        Each coordinator uses its own start-store connection; the route is
        already persistently ROUTE_SELECTED. Returns per-thread outcomes.
        """
        outcomes = [None] * n_threads
        barrier = threading.Barrier(n_threads)

        def worker(idx):
            st = self._thread_start_store()
            a_store = self._auth_store()
            barrier.wait()
            try:
                res = reserve_execution_start(
                    store=a_store, start_store=st,
                    attempt_id=self.attempt_id,
                    launcher_actor=launcher_for_idx(idx),
                    clock=lambda: self.clock)
                outcomes[idx] = res
            except Exception as exc:  # noqa: BLE001
                outcomes[idx] = exc
            finally:
                st.close()
                a_store.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        return outcomes

    def test_race_identical_context(self):
        # All same launcher -> exactly one winner, all replay to same reservation.
        outcomes = self._race(8)
        winners = [o for o in outcomes if isinstance(o, ExecutionStartReservation)]
        errors = [o for o in outcomes if isinstance(o, ExecutionStartConflictError)]
        self.assertEqual(len(winners), 8, "all identical racers should converge on the reservation")
        self.assertEqual(len(errors), 0)
        # All returned reservations are the SAME durable artifact.
        ids = {o.reservation_id for o in winners}
        self.assertEqual(len(ids), 1)
        self._assert_exactly_one()
        self._no_sqlite_leak(outcomes)

    def test_race_conflicting_launcher(self):
        # Two different launchers race; exactly one wins, the other conflicts.
        outcomes = self._race(2, launcher_for_idx=lambda i: _make_launcher(
            actor_id=f"launcher-{i}"))
        winners = [o for o in outcomes if isinstance(o, ExecutionStartReservation)]
        conflicts = [o for o in outcomes if isinstance(o, ExecutionStartConflictError)]
        self.assertEqual(len(winners), 1, "exactly one launcher should win")
        self.assertEqual(len(conflicts), 1, "the divergent launcher must conflict")
        self._assert_exactly_one()
        self._no_sqlite_leak(outcomes)

    def test_race_expired_deadline(self):
        # Same attempt, but route must_start_by already passed at admission.
        self.clock = "2099-01-02T00:00:00Z"
        outcomes = self._race(4)
        expired = [o for o in outcomes if isinstance(o, ExecutionStartExpiredError)]
        self.assertEqual(len(expired), 4, "all should fail the expired deadline")
        self._assert_zero()

    def test_replay_wave(self):
        st = self._thread_start_store()
        a_store = self._auth_store()
        first = reserve_execution_start(
            store=a_store, start_store=st, attempt_id=self.attempt_id,
            launcher_actor=self.launcher, clock=lambda: self.clock)
        # Repeated identical calls replay to the same reservation.
        for _ in range(5):
            again = reserve_execution_start(
                store=a_store, start_store=st, attempt_id=self.attempt_id,
                launcher_actor=self.launcher, clock=lambda: self.clock)
            self.assertEqual(again.reservation_id, first.reservation_id)
        st.close()
        a_store.close()
        self._assert_exactly_one()

    def test_no_launch_attempt_written(self):
        st = self._thread_start_store()
        a_store = self._auth_store()
        res = reserve_execution_start(
            store=a_store, start_store=st, attempt_id=self.attempt_id,
            launcher_actor=self.launcher, clock=lambda: self.clock)
        self.assertFalse(st.has_launch_attempt(res.reservation_id))
        st.close()
        a_store.close()

    def _assert_zero(self):
        st = self._thread_start_store()
        self.assertEqual(len(st.get_reservations_for_route(self.route.route_id)), 0)
        self.assertEqual(len(st.get_start_ledger_events("START_RESERVED")), 0)
        st.close()


if __name__ == "__main__":
    unittest.main()
