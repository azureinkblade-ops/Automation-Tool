"""EA-4C.1: WorkerRouter domain + immutable routing artifacts (pure tests).

This slice is DOMAIN ONLY. It covers the immutable artifacts:

* ``WorkerDescriptor`` (structured, hash-bound worker identity);
* ``WorkerRegistry`` (versioned, tamper-evident snapshot);
* ``WorkerRouterActor`` / ``WorkerRouterActorType`` (bounded routing identity);
* ``WorkerRouteDecision`` (immutable, hash-bound routing artifact);
* canonical hashing + reconstruction round-trips;
* the typed error taxonomy (incl. ``WorkerRouteNoEligibleWorkerError`` type).

It does NOT test worker eligibility evaluation or route selection -- those
belong to EA-4C.3 (Routing Policy and Selection). No persistence, no launch,
no clock/runtime evaluation, no connection/thread concurrency.
"""

import unittest
from typing import Optional

from tools.hermes_core import worker_router
from tools.hermes_core.execution_authorization import ExecutionAuthorizationScope
from tools.hermes_core.worker_router import (
    ROUTE_ARTIFACT_VERSION,
    WorkerDescriptor,
    WorkerRegistry,
    WorkerRouteDecision,
    WorkerRouteError,
    WorkerRouteNoEligibleWorkerError,
    WorkerRouterActor,
    WorkerRouterActorType,
    WorkerRoutingPolicyRef,
    WorkerRouteStatus,
    build_worker_descriptor,
    build_worker_registry,
    build_worker_route_decision,
    reconstruct_worker_descriptor,
    reconstruct_worker_registry,
    reconstruct_worker_route_decision,
    verify_worker_route_decision_hash,
)


def _make_policy() -> WorkerRoutingPolicyRef:
    return WorkerRoutingPolicyRef(
        policy_id="route-policy-1",
        policy_version="1",
        policy_hash="phash-1",
    )


def _make_router_actor() -> WorkerRouterActor:
    return WorkerRouterActor(
        actor_id="router-1",
        actor_type=WorkerRouterActorType.SYSTEM_ROUTER,
        actor_context="ea4c-domain",
    )


def _make_w_a() -> WorkerDescriptor:
    return build_worker_descriptor(
        worker_id="w-a",
        worker_class="render-worker",
        worker_version="1.0.0",
        capabilities=["render"],
        allowed_operations=["render"],
        enabled=True,
        registration_source="static",
        registration_version="reg-1",
    )


def _make_w_b() -> WorkerDescriptor:
    return build_worker_descriptor(
        worker_id="w-b",
        worker_class="render-worker",
        worker_version="1.0.1",
        capabilities=["render"],
        allowed_operations=["render", "transcode"],
        enabled=True,
        registration_source="static",
        registration_version="reg-1",
    )


def _make_registry() -> WorkerRegistry:
    return build_worker_registry(
        registry_version="reg-1",
        workers=[_make_w_a(), _make_w_b()],
    )


def _make_scope(
    *,
    worker_class: str = "render-worker",
    operation: str = "render",
    input_hash: str = "in-abc",
) -> ExecutionAuthorizationScope:
    return ExecutionAuthorizationScope(
        operation=operation,
        worker_class=worker_class,
        input_hash=input_hash,
        attempt_limit=1,
        max_runtime_seconds=None,
    )


def _make_route_decision() -> WorkerRouteDecision:
    """A valid (but domain-only) route artifact assembled by the constructor.

    This exercises the immutable-artifact constructor, NOT selection logic.
    """
    reg = _make_registry()
    return build_worker_route_decision(
        attempt_id="att-1",
        attempt_hash="ah",
        authorization_id="auth-1",
        authorization_hash="authh",
        claim_id="clm-1",
        claim_hash="clmh",
        request_id="req-1",
        request_hash="reqh",
        decision_id="dec-1",
        decision_hash="dech",
        task_id="task-1",
        worker_id="w-a",
        worker_class="render-worker",
        registry=reg,
        policy=_make_policy(),
        selected_at="2026-08-15T12:00:00Z",
        must_start_by="2026-08-15T13:00:00Z",
        operation="render",
        input_hash="in-abc",
        router_actor=_make_router_actor(),
    )


class WorkerRouterActorDomainTests(unittest.TestCase):
    def test_router_actor_type_enum(self):
        self.assertEqual(
            WorkerRouterActorType.SYSTEM_ROUTER.value, "SYSTEM_ROUTER"
        )
        self.assertEqual(
            WorkerRouterActorType.POLICY_SERVICE.value, "POLICY_SERVICE"
        )

    def test_router_actor_to_dict(self):
        actor = _make_router_actor()
        d = actor.to_dict()
        self.assertEqual(d["actor_id"], "router-1")
        self.assertEqual(d["actor_type"], "SYSTEM_ROUTER")
        self.assertEqual(d["actor_context"], "ea4c-domain")

    def test_system_router_distinct_from_generic_system(self):
        # SYSTEM_ROUTER is a bounded routing-domain identity, not a general
        # SYSTEM authority principal.
        self.assertNotEqual(
            WorkerRouterActorType.SYSTEM_ROUTER.value, "SYSTEM"
        )
        self.assertTrue(
            WorkerRouterActorType.SYSTEM_ROUTER.value.startswith("SYSTEM_")
        )


class WorkerDescriptorDomainTests(unittest.TestCase):
    def test_descriptor_hash_bound(self):
        d = _make_w_a()
        self.assertTrue(d.verify_hash())
        # Tampering a field invalidates the hash.
        full = {**d.to_canonical_dict(), "descriptor_hash": d.descriptor_hash}
        full["enabled"] = False
        bad = reconstruct_worker_descriptor(full)
        self.assertFalse(bad.verify_hash())

    def test_descriptor_reconstruct_roundtrip(self):
        d = _make_w_a()
        full = {**d.to_canonical_dict(), "descriptor_hash": d.descriptor_hash}
        r = reconstruct_worker_descriptor(full)
        self.assertEqual(r, d)
        self.assertEqual(r.descriptor_hash, d.descriptor_hash)

    def test_descriptor_identity_not_executable(self):
        d = _make_w_a()
        # Identity is the registered worker_id/worker_class, never a path/cmd.
        self.assertNotIn("/", d.worker_id)
        self.assertNotIn("cmd", d.to_canonical_dict())


class WorkerRegistryDomainTests(unittest.TestCase):
    def test_registry_hash_bound(self):
        reg = _make_registry()
        self.assertTrue(reg.verify_hash())
        # Tampering a worker invalidates the registry hash.
        w_full = {**_make_w_a().to_canonical_dict(), "descriptor_hash": _make_w_a().descriptor_hash}
        w_full["enabled"] = False
        tampered_workers = [reconstruct_worker_descriptor(w_full)]
        bad = WorkerRegistry(
            registry_version=reg.registry_version,
            registry_hash=reg.registry_hash,
            workers=tampered_workers,
        )
        self.assertFalse(bad.verify_hash())

    def test_registry_reconstruct_roundtrip(self):
        reg = _make_registry()
        full = {**reg.to_canonical_dict(), "registry_hash": reg.registry_hash}
        r = reconstruct_worker_registry(full)
        self.assertEqual(r, reg)
        self.assertEqual(r.registry_hash, reg.registry_hash)


class WorkerRouteDecisionDomainTests(unittest.TestCase):
    def test_route_artifact_version_and_status(self):
        self.assertEqual(ROUTE_ARTIFACT_VERSION, "1")
        self.assertEqual(WorkerRouteStatus.SELECTED.value, "SELECTED")

    def test_route_status_vocabulary_is_selection_only(self):
        # EA-4C stops at SELECTED; no execution-state vocabulary exists.
        allowed = {s.value for s in WorkerRouteStatus}
        for forbidden in ("EXECUTING", "RUNNING", "STARTED", "SUCCEEDED", "FAILED", "CANCELLED"):
            self.assertNotIn(forbidden, allowed)

    def test_route_hash_binds_full_lineage(self):
        decision = _make_route_decision()
        self.assertTrue(verify_worker_route_decision_hash(decision))
        # Tampering any bound field invalidates the hash. Reconstruct via the
        # canonical reconstructor, which re-binds the enum status correctly.
        tampered = reconstruct_worker_route_decision(
            {
                **decision.to_canonical_dict(),
                "artifact_hash": decision.artifact_hash,
                "worker_id": "w-changed",
            }
        )
        self.assertFalse(verify_worker_route_decision_hash(tampered))

    def test_route_reconstruct_roundtrip(self):
        decision = _make_route_decision()
        full = {**decision.to_canonical_dict(), "artifact_hash": decision.artifact_hash}
        r = reconstruct_worker_route_decision(full)
        self.assertEqual(r, decision)
        self.assertEqual(r.artifact_hash, decision.artifact_hash)
        self.assertEqual(r.status.value, "SELECTED")

    def test_route_binds_registry_and_policy_refs(self):
        decision = _make_route_decision()
        self.assertEqual(decision.worker_registry_version, "reg-1")
        self.assertTrue(decision.worker_registry_hash)
        self.assertEqual(decision.routing_policy_id, "route-policy-1")
        self.assertEqual(decision.routing_policy_version, "1")
        self.assertEqual(decision.routing_policy_hash, "phash-1")

    def test_route_binds_router_actor_identity(self):
        decision = _make_route_decision()
        self.assertEqual(decision.router_actor_id, "router-1")
        self.assertEqual(decision.router_actor_type, "SYSTEM_ROUTER")
        self.assertEqual(decision.router_actor_context, "ea4c-domain")


class WorkerRouteErrorTaxonomyTests(unittest.TestCase):
    def test_error_hierarchy_is_value_error(self):
        from tools.hermes_core.worker_router import (
            WorkerRouteConflictError,
            WorkerRouteError,
            WorkerRouteExpiredError,
            WorkerRouteIntegrityError,
            WorkerRouteLineageError,
            WorkerRouteNotFoundError,
            WorkerRoutePolicyError,
            WorkerRegistryIntegrityError,
            WorkerRegistryVersionError,
        )

        for exc in (
            WorkerRouteNotFoundError(),
            WorkerRouteConflictError(),
            WorkerRouteExpiredError(),
            WorkerRouteIntegrityError(),
            WorkerRouteLineageError(),
            WorkerRoutePolicyError(),
            WorkerRegistryIntegrityError(),
            WorkerRegistryVersionError(),
            WorkerRouteNoEligibleWorkerError(),
        ):
            self.assertIsInstance(exc, WorkerRouteError)
            self.assertIsInstance(exc, ValueError)

    def test_no_eligible_worker_error_is_typed_and_non_persisted(self):
        err = WorkerRouteNoEligibleWorkerError("none")
        self.assertIsInstance(err, WorkerRouteError)
        # Non-persisted: it carries no route_id / artifact_hash of its own.
        self.assertFalse(hasattr(err, "route_id"))


class WorkerRouterCapabilityNegativeTests(unittest.TestCase):
    def test_no_execution_capability_in_code(self):
        """No real execution capability may appear as a code identifier.

        Negative assertions in docstrings/comments that document ABSENCE are
        explicitly permitted by the EA-4C design packet (not leakage). This
        test mirrors the EA-4B convention: scan AST identifiers, not prose.
        """
        import ast
        import inspect

        from tools.hermes_core import worker_router

        tree = ast.parse(inspect.getsource(worker_router))
        forbidden_idents = {
            "subprocess",
            "Popen",
            "os",
            "enqueue",
            "dispatch",
            "launch",
            "spawn",
            "queue",
            "exec",
            "select_worker_route",
            "select",
        }
        found = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, ast.FunctionDef):
                found.add(node.name)
            elif isinstance(node, ast.ClassDef):
                found.add(node.name)
        for token in forbidden_idents:
            self.assertNotIn(token, found)

    def test_no_worker_selection_function_exists(self):
        # EA-4C.1 must NOT provide a route-selection service.
        self.assertFalse(hasattr(worker_router, "select_worker_route"))


if __name__ == "__main__":
    unittest.main()
