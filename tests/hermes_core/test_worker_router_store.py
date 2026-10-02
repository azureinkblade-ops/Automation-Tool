"""EA-4C.2: WorkerRouter persistence (route record + ledger + read APIs).

Persistence-only slice. These tests prove:

* a hash-bound WorkerRouteDecision (already constructed) is persisted with
  exactly one ROUTE_SELECTED ledger event;
* one durable route per Attempt (UNIQUE attempt_id) -- a second route for the
  same Attempt fails closed with a conflict;
* storage-level lineage: the referenced Attempt must exist with a matching
  attempt_hash, else fail closed;
* tampering a physical binding column after persistence is detected on load;
* rollback injection after the route INSERT leaves zero route rows and zero
  ROUTE_SELECTED events;
* read APIs return integrity-verified artifacts.

They do NOT cover worker eligibility, deterministic selection, or current-time
admission -- those belong to EA-4C.3. No execution capability is present.
"""

import os
import tempfile
import unittest

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
    consume_claim_into_attempt,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    ExecutionAuthorizationConflictError,
    ExecutionAuthorizationIntegrityError,
    ExecutionAuthorizationLineageError,
    ExecutionAuthorizationStoreError,
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.worker_router import (
    WorkerDescriptor,
    WorkerRegistry,
    WorkerRouteDecision,
    WorkerRouterActor,
    WorkerRouterActorType,
    WorkerRoutingPolicyRef,
    build_worker_descriptor,
    build_worker_registry,
    build_worker_route_decision,
    reconstruct_worker_route_decision,
)


def _h(s: str) -> str:
    """Deterministic 64-char lowercase-hex placeholder (NOT a real hash)."""
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# -- EA-4B prerequisite chain (mirrors test_execution_authorization_attempt_concurrent) --

def _make_scope(attempt_limit=1) -> ExecutionAuthorizationScope:
    return ExecutionAuthorizationScope(
        operation="run-sandboxed",
        worker_class="render-worker",
        input_hash=_h("in"),
        attempt_limit=attempt_limit,
        max_runtime_seconds=300,
    )


def _make_policy() -> ExecutionAuthorizationPolicyRef:
    return ExecutionAuthorizationPolicyRef(policy_id="ea-baseline", policy_version="1.0")


def _make_actor() -> ExecutionAuthorizationActor:
    return ExecutionAuthorizationActor(
        actor_id="human-owner",
        actor_type=ExecutionAuthorizationActorType.HUMAN,
        authority_role="owner",
        authentication_context=None,
    )


def _make_attempt_actor() -> ExecutionAttemptActor:
    return ExecutionAttemptActor(
        actor_id="runtime-orchestrator", actor_type="SYSTEM", actor_context="node-1"
    )


def _setup_claim_lineage(store: SQLiteExecutionAuthorizationStore, task_id="task-1"):
    """Build request -> granted decision + authorization -> claim (persisted)."""
    policy = _make_policy()
    actor = _make_actor()
    scope = _make_scope(attempt_limit=1)
    acc_id = "acceptance-" + "b" * 16
    acc_hash = _h("acc")

    req = build_execution_authorization_request(
        task_id=task_id,
        accepted_governance_artifact_id=acc_id,
        accepted_governance_hash=acc_hash,
        requested_scope=scope,
        requesting_actor=actor,
        authorization_policy=policy,
        requested_at="2026-08-12T21:25:00Z",
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
        request_id=dec.request_id,
        request_hash=dec.request_hash,
        decision_id=dec.decision_id,
        decision_hash=dec.artifact_hash,
        authorization_actor=actor,
        authorized_scope=scope,
        authorization_reason="operator approved",
        authorization_policy=policy,
        issued_at="2026-08-12T21:30:00Z",
        expires_at="2026-08-12T22:00:00Z",
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
        claimed_at="2026-08-12T21:30:00Z",
        claim_expires_at="2026-08-12T22:00:00Z",
        authorization_policy=policy,
        claim_reason="claim by worker-manager",
    )
    store.claim_authorization_atomically(auth.authorization_id, claim)
    return auth, claim


def _persisted_attempt(store: SQLiteExecutionAuthorizationStore):
    """Build + persist a real Attempt (via consume_claim_transaction)."""
    auth, claim = _setup_claim_lineage(store)
    result = consume_claim_into_attempt(
        store=store,
        authorization_id=auth.authorization_id,
        claim_id=claim.claim_id,
        claimant=_make_attempt_actor(),
        must_start_within_seconds=300,
        clock=lambda: "2026-08-12T21:31:00Z",
    )
    return store.get_attempt(result.attempt_id)


def _registry() -> WorkerRegistry:
    w = build_worker_descriptor(
        worker_id="w-a",
        worker_class="render-worker",
        worker_version="1.0.0",
        capabilities=["render"],
        allowed_operations=["render"],
        enabled=True,
        registration_source="static",
        registration_version="reg-1",
    )
    return build_worker_registry(registry_version="reg-1", workers=[w])


def _policy() -> WorkerRoutingPolicyRef:
    return WorkerRoutingPolicyRef(
        policy_id="route-policy-1", policy_version="1", policy_hash="phash-1"
    )


def _router_actor() -> WorkerRouterActor:
    return WorkerRouterActor(
        actor_id="router-1",
        actor_type=WorkerRouterActorType.SYSTEM_ROUTER,
        actor_context="ea4c-store",
    )


def _make_route(store: SQLiteExecutionAuthorizationStore, attempt) -> WorkerRouteDecision:
    return build_worker_route_decision(
        attempt_id=attempt.attempt_id,
        attempt_hash=attempt.artifact_hash,
        authorization_id=attempt.authorization_id,
        authorization_hash=attempt.authorization_hash,
        claim_id=attempt.claim_id,
        claim_hash=attempt.claim_hash,
        request_id=attempt.request_id,
        request_hash=attempt.request_hash,
        decision_id=attempt.decision_id,
        decision_hash=attempt.decision_hash,
        task_id=attempt.task_id,
        worker_id="w-a",
        worker_class="render-worker",
        registry=_registry(),
        policy=_policy(),
        selected_at="2026-08-15T12:00:00Z",
        must_start_by=attempt.must_start_by,
        operation=attempt.operation,
        input_hash=attempt.input_hash,
        router_actor=_router_actor(),
    )


class WorkerRoutePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "ea.db")
        self.store = SQLiteExecutionAuthorizationStore(self.db)

    def tearDown(self):
        self.store.close()

    def _persisted_attempt(self):
        """Build + persist a real Attempt (module-level chain) so a route can bind."""
        return _persisted_attempt(self.store)

    def test_record_route_persists_with_single_ledger_event(self):
        attempt = self._persisted_attempt()
        route = _make_route(self.store, attempt)
        self.store.record_route(route)
        # Read back; integrity-verified equal.
        loaded = self.store.get_route(route.route_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded, route)
        # Exactly one ROUTE_SELECTED ledger event.
        events = self.store.get_ledger_events(event_type="ROUTE_SELECTED")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].artifact_id, route.route_id)
        self.assertEqual(events[0].artifact_hash, route.artifact_hash)

    def test_get_route_for_attempt(self):
        attempt = self._persisted_attempt()
        route = _make_route(self.store, attempt)
        self.store.record_route(route)
        loaded = self.store.get_route_for_attempt(attempt.attempt_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.route_id, route.route_id)

    def test_get_routes_for_worker(self):
        attempt = self._persisted_attempt()
        route = _make_route(self.store, attempt)
        self.store.record_route(route)
        routes = self.store.get_routes_for_worker("w-a")
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].worker_id, "w-a")

    def test_route_requires_existing_attempt(self):
        # Route references an Attempt ID that was never persisted.
        route = build_worker_route_decision(
            attempt_id="nonexistent-attempt",
            attempt_hash=_h("nonexistent"),
            authorization_id="auth-1",
            authorization_hash=_h("auth-1"),
            claim_id="clm-1",
            claim_hash=_h("clm-1"),
            request_id="req-1",
            request_hash=_h("req-1"),
            decision_id="dec-1",
            decision_hash=_h("dec-1"),
            task_id="task-1",
            worker_id="w-a",
            worker_class="render-worker",
            registry=_registry(),
            policy=_policy(),
            selected_at="2026-08-15T12:00:00Z",
            must_start_by="2026-08-15T13:00:00Z",
            operation="render",
            input_hash=_h("in"),
            router_actor=_router_actor(),
        )
        with self.assertRaises(ExecutionAuthorizationStoreError):
            self.store.record_route(route)

    def test_route_attempt_hash_mismatch_fails_lineage(self):
        # Persist a REAL attempt, then build a route whose attempt_hash does
        # NOT match the persisted attempt's hash. Storage-level lineage fails
        # closed (this is NOT selection -- just binding integrity).
        attempt = self._persisted_attempt()
        route = build_worker_route_decision(
            attempt_id=attempt.attempt_id,
            attempt_hash="0" * 64,  # wrong hash for the persisted attempt
            authorization_id=attempt.authorization_id,
            authorization_hash=attempt.authorization_hash,
            claim_id=attempt.claim_id,
            claim_hash=attempt.claim_hash,
            request_id=attempt.request_id,
            request_hash=attempt.request_hash,
            decision_id=attempt.decision_id,
            decision_hash=attempt.decision_hash,
            task_id=attempt.task_id,
            worker_id="w-a",
            worker_class="render-worker",
            registry=_registry(),
            policy=_policy(),
            selected_at="2026-08-15T12:00:00Z",
            must_start_by=attempt.must_start_by,
            operation=attempt.operation,
            input_hash=attempt.input_hash,
            router_actor=_router_actor(),
        )
        with self.assertRaises(ExecutionAuthorizationLineageError):
            self.store.record_route(route)

    def test_one_route_per_attempt_conflicts(self):
        attempt = self._persisted_attempt()
        route = _make_route(self.store, attempt)
        self.store.record_route(route)
        # A second route for the SAME attempt must conflict (UNIQUE attempt_id).
        route2 = build_worker_route_decision(
            attempt_id=attempt.attempt_id,
            attempt_hash=attempt.artifact_hash,
            authorization_id=attempt.authorization_id,
            authorization_hash=attempt.authorization_hash,
            claim_id=attempt.claim_id,
            claim_hash=attempt.claim_hash,
            request_id=attempt.request_id,
            request_hash=attempt.request_hash,
            decision_id=attempt.decision_id,
            decision_hash=attempt.decision_hash,
            task_id=attempt.task_id,
            worker_id="w-a",
            worker_class="render-worker",
            registry=_registry(),
            policy=_policy(),
            selected_at="2026-08-15T12:00:00Z",
            must_start_by=attempt.must_start_by,
            operation=attempt.operation,
            input_hash=attempt.input_hash,
            router_actor=_router_actor(),
        )
        with self.assertRaises(ExecutionAuthorizationConflictError):
            self.store.record_route(route2)
        # Still exactly one ROUTE_SELECTED event, one route row.
        self.assertEqual(
            len(self.store.get_ledger_events(event_type="ROUTE_SELECTED")), 1
        )
        self.assertEqual(len(self.store.get_routes_for_worker("w-a")), 1)

    def test_tamper_physical_column_detected_on_load(self):
        import sqlite3

        attempt = self._persisted_attempt()
        route = _make_route(self.store, attempt)
        self.store.record_route(route)
        # Tamper a physical binding column directly in the DB.
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE worker_routes SET worker_id = 'tampered' WHERE attempt_id = ?",
            (attempt.attempt_id,),
        )
        conn.commit()
        conn.close()
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_route(route.route_id)

    # -- full physical linkage envelope: tamper of each previously-omitted
    #    physical column must break the route_linkage_sha256 envelope --

    def _tamper_and_assert_detected(self, column, value):
        import sqlite3

        attempt = self._persisted_attempt()
        route = _make_route(self.store, attempt)
        self.store.record_route(route)
        conn = sqlite3.connect(self.db)
        conn.execute(
            f"UPDATE worker_routes SET {column} = ? WHERE attempt_id = ?",
            (value, attempt.attempt_id),
        )
        conn.commit()
        conn.close()
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_route(route.route_id)

    def test_tamper_artifact_hash_detected(self):
        self._tamper_and_assert_detected("artifact_hash", "0" * 64)

    def test_tamper_artifact_version_detected(self):
        self._tamper_and_assert_detected("artifact_version", "99")

    def test_tamper_selected_at_detected(self):
        self._tamper_and_assert_detected("selected_at", "2099-01-01T00:00:00Z")

    def test_tamper_must_start_by_detected(self):
        self._tamper_and_assert_detected("must_start_by", "2099-01-01T00:00:00Z")

    def test_tamper_operation_detected(self):
        self._tamper_and_assert_detected("operation", "compromised")

    def test_tamper_input_hash_detected(self):
        self._tamper_and_assert_detected("input_hash", "f" * 64)

    # -- full Attempt lineage enforcement: each upstream field that the route
    #    binds must EQUAL the durable Attempt, else fail closed --

    def _route_with_mismatched_field(self, attempt, field, value):
        kwargs = dict(
            attempt_id=attempt.attempt_id,
            attempt_hash=attempt.artifact_hash,
            authorization_id=attempt.authorization_id,
            authorization_hash=attempt.authorization_hash,
            claim_id=attempt.claim_id,
            claim_hash=attempt.claim_hash,
            request_id=attempt.request_id,
            request_hash=attempt.request_hash,
            decision_id=attempt.decision_id,
            decision_hash=attempt.decision_hash,
            task_id=attempt.task_id,
            worker_id="w-a",
            worker_class=attempt.worker_class,
            registry=_registry(),
            policy=_policy(),
            selected_at="2026-08-15T12:00:00Z",
            must_start_by=attempt.must_start_by,
            operation=attempt.operation,
            input_hash=attempt.input_hash,
            router_actor=_router_actor(),
        )
        kwargs[field] = value
        return build_worker_route_decision(**kwargs)

    def _assert_mismatch_rejected(self, field, value):
        attempt = self._persisted_attempt()
        route = self._route_with_mismatched_field(attempt, field, value)
        with self.assertRaises(ExecutionAuthorizationLineageError):
            self.store.record_route(route)

    def test_lineage_mismatch_authorization_id(self):
        self._assert_mismatch_rejected("authorization_id", "tampered-auth")

    def test_lineage_mismatch_authorization_hash(self):
        self._assert_mismatch_rejected("authorization_hash", "0" * 64)

    def test_lineage_mismatch_claim_id(self):
        self._assert_mismatch_rejected("claim_id", "tampered-claim")

    def test_lineage_mismatch_claim_hash(self):
        self._assert_mismatch_rejected("claim_hash", "0" * 64)

    def test_lineage_mismatch_request_id(self):
        self._assert_mismatch_rejected("request_id", "tampered-req")

    def test_lineage_mismatch_request_hash(self):
        self._assert_mismatch_rejected("request_hash", "0" * 64)

    def test_lineage_mismatch_decision_id(self):
        self._assert_mismatch_rejected("decision_id", "tampered-dec")

    def test_lineage_mismatch_decision_hash(self):
        self._assert_mismatch_rejected("decision_hash", "0" * 64)

    def test_lineage_mismatch_task_id(self):
        self._assert_mismatch_rejected("task_id", "tampered-task")

    def test_lineage_mismatch_operation(self):
        self._assert_mismatch_rejected("operation", "tampered-op")

    def test_lineage_mismatch_input_hash(self):
        self._assert_mismatch_rejected("input_hash", "f" * 64)

    def test_lineage_mismatch_worker_class(self):
        self._assert_mismatch_rejected("worker_class", "tampered-class")

    def test_rollback_injection_leaves_zero_residue(self):
        attempt = self._persisted_attempt()
        route = _make_route(self.store, attempt)
        self.store._fail_after_route_insert = True
        with self.assertRaises(RuntimeError):
            self.store.record_route(route)
        self.store._fail_after_route_insert = False
        # Zero route rows, zero ROUTE_SELECTED events.
        self.assertIsNone(self.store.get_route_for_attempt(attempt.attempt_id))
        self.assertEqual(
            len(self.store.get_ledger_events(event_type="ROUTE_SELECTED")), 0
        )
        # A subsequent valid write succeeds normally.
        self.store.record_route(route)
        self.assertEqual(
            len(self.store.get_routes_for_worker("w-a")), 1
        )


    def test_verify_integrity_clean_after_route(self):
        # A clean DB with one persisted route passes verify_integrity.
        attempt = self._persisted_attempt()
        route = _make_route(self.store, attempt)
        self.store.record_route(route)
        report = self.store.verify_integrity()
        self.assertTrue(report.ok, msg=report.failures)

    def test_verify_integrity_detects_route_tamper(self):
        import sqlite3

        attempt = self._persisted_attempt()
        route = _make_route(self.store, attempt)
        self.store.record_route(route)
        # Tamper a physical column directly.
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE worker_routes SET worker_id = 'tampered' WHERE attempt_id = ?",
            (attempt.attempt_id,),
        )
        conn.commit()
        conn.close()
        report = self.store.verify_integrity()
        self.assertFalse(report.ok)
        self.assertTrue(
            any("route linkage tamper" in f for f in report.failures)
        )


class WorkerRoutePersistenceCapabilityNegativeTests(unittest.TestCase):
    def test_no_selection_or_eligibility_or_clock_admission(self):
        """No selection / eligibility / current-time admission in code.

        Negative docstring prose describing absence is permitted (packet
        §21). Mirror the EA-4C.1 convention: scan AST identifiers, not prose.
        """
        import ast
        import inspect

        from tools.hermes_core import sqlite_execution_authorization_store as mod
        from tools.hermes_core import worker_router

        store_src = inspect.getsource(mod)
        router_src = inspect.getsource(worker_router)

        forbidden_substrings = (
            "select_worker_route",
            "subprocess",
            "Popen",
            "os.system",
            "EXECUTION_ATTEMPT_STARTED",
            "Ollama",
            "Playwright",
        )
        for token in forbidden_substrings:
            self.assertNotIn(token, store_src)
            self.assertNotIn(token, router_src)

        # AST identifier scan: no eligibility/selection function or method.
        forbidden_idents = {
            "eligible",
            "is_eligible",
            "select_worker",
            "select_route",
        }
        for src in (store_src, router_src):
            tree = ast.parse(src)
            found = {
                node.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Name)
            }
            found |= {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
            }
            found |= {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.ClassDef))
            }
            for token in forbidden_idents:
                self.assertNotIn(token, found)


class WorkerRouteSchemaVersionTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ea.db")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_schema_5_fails_closed(self):
        # EA-4B produced schema-5 authority DBs (no worker_routes table). A v6
        # reader must fail closed on a v5 DB -- it must NOT silently open a DB
        # it cannot fully interpret, nor auto-migrate. Immediate-predecessor
        # downgrade case for EA-4C.2's schema-6 bump. (v1-v4 and future/99 are
        # covered by the EA-4B attempt-store schema tests.)
        import sqlite3

        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE authority_schema_version (version INTEGER)")
        conn.execute("INSERT INTO authority_schema_version (version) VALUES (5)")
        conn.commit()
        conn.close()
        with self.assertRaises(Exception):
            SQLiteExecutionAuthorizationStore(self.db)


if __name__ == "__main__":
    unittest.main()
