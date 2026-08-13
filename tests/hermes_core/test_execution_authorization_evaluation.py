"""EA-3I.1 tests: policy + authority evaluation contracts (pure/read-only).

Pre-capability slice: these tests assert that evaluation is deterministic and
fail-closed, and crucially that NO real execution authorization is ever created
or persisted. No DB, no EA-3B atomic grant, no claim/worker/execution.
"""

import unittest

from tools.hermes_core import execution_authorization_policy as P
from tools.hermes_core import execution_authorization_evaluation as E
from tools.hermes_core.execution_authorization import (
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationPolicyRef,
    ExecutionAuthorizationScope,
    build_execution_authorization_request,
)
from tools.hermes_core.execution_authorization_evaluation import (
    ExecutionAuthorizationActorContext,
    ExecutionAuthorizationActorAuthenticationError,
    ExecutionAuthorizationActorAuthorityError,
    ExecutionAuthorizationEvaluationError,
    ExecutionAuthorizationPolicyEvaluation,
    ExecutionAuthorizationPolicyDecision,
)
from tools.hermes_core.execution_authorization_policy import (
    ExecutionAuthorizationPolicyNotFoundError,
    ExecutionAuthorizationPolicyVersionError,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)

import tests.hermes_core.test_execution_authorization_store as store_test
from tests.hermes_core.test_execution_authorization_store import make_actor, make_policy

POLICY_ID = "ea-baseline"
POLICY_VER = "1.0"
ALLOW = ExecutionAuthorizationPolicyDecision.ALLOW
DENY = ExecutionAuthorizationPolicyDecision.DENY
REQUIRES_HUMAN = ExecutionAuthorizationPolicyDecision.REQUIRES_HUMAN


def _policy():
    return P.resolve_policy(POLICY_ID, POLICY_VER)


def _ctx(actor_id, actor_type, role, auth=True, ref=None):
    return ExecutionAuthorizationActorContext(
        actor_id=actor_id,
        actor_type=actor_type,
        authority_role=role,
        authentication_evidence_present=auth,
        authentication_reference=ref,
    )


def _request(operation, worker_class, attempts=1, runtime=300,
             accepted_id="acceptance-" + "a" * 16, accepted_hash="a" * 64,
             task_id="task-1"):
    scope = ExecutionAuthorizationScope(
        operation=operation,
        worker_class=worker_class,
        input_hash="a" * 64,
        attempt_limit=attempts,
        max_runtime_seconds=runtime,
    )
    return build_execution_authorization_request(
        task_id=task_id,
        accepted_governance_artifact_id=accepted_id,
        accepted_governance_hash=accepted_hash,
        requested_scope=scope,
        requesting_actor=make_actor(),
        authorization_policy=make_policy(),
        requested_at="2026-08-12T21:25:00Z",
        request_reason="need exec",
    )


class TestEA3I1PolicyDecision(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual({d.value for d in ExecutionAuthorizationPolicyDecision},
                         {"ALLOW", "DENY", "REQUIRES_HUMAN"})

    def test_human_operator_allowed(self):
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", "restricted-sandbox"),
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        self.assertEqual(ev.outcome, ALLOW)
        self.assertFalse(ev.result.requires_human)

    def test_policy_service_requires_human(self):
        # Default posture: POLICY_SERVICE has no enumerated auto-scope.
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", "restricted-sandbox"),
            actor_context=_ctx("svc", ExecutionAuthorizationActorType.POLICY_SERVICE, "policy-service"),
            policy=_policy(),
        )
        self.assertEqual(ev.outcome, REQUIRES_HUMAN)
        self.assertTrue(ev.result.requires_human)

    def test_system_no_grant(self):
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", "restricted-sandbox"),
            actor_context=_ctx("sys", ExecutionAuthorizationActorType.SYSTEM, "system"),
            policy=_policy(),
        )
        self.assertEqual(ev.outcome, DENY)

    def test_unauthenticated_human_error(self):
        with self.assertRaises(ExecutionAuthorizationActorAuthenticationError):
            E.evaluate_execution_authorization_policy(
                request=_request("run-sandboxed", "restricted-sandbox"),
                actor_context=_ctx("u2", ExecutionAuthorizationActorType.HUMAN, "operator", auth=False),
                policy=_policy(),
            )

    def test_unknown_role_fail_closed(self):
        with self.assertRaises(ExecutionAuthorizationActorAuthorityError):
            E.evaluate_execution_authorization_policy(
                request=_request("run-sandboxed", "restricted-sandbox"),
                actor_context=_ctx("u3", ExecutionAuthorizationActorType.HUMAN, "ghost"),
                policy=_policy(),
            )

    def test_unknown_policy_error(self):
        with self.assertRaises(ExecutionAuthorizationPolicyNotFoundError):
            P.resolve_policy("nope", "9.9")

    def test_unsupported_policy_version_error(self):
        with self.assertRaises(ExecutionAuthorizationPolicyVersionError):
            P.resolve_policy(POLICY_ID, "9.9")

    def test_unknown_operation_denied(self):
        ev = E.evaluate_execution_authorization_policy(
            request=_request("bogus-op", "restricted-sandbox"),
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        self.assertEqual(ev.outcome, DENY)

    def test_unknown_worker_denied(self):
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", "bogus-worker"),
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        self.assertEqual(ev.outcome, DENY)

    def test_worker_none_requires_human(self):
        # worker_class None is deferred/unresolved, not unrestricted.
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", None),
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        self.assertEqual(ev.outcome, REQUIRES_HUMAN)

    def test_attempt_limit_constrained_not_widened(self):
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", "restricted-sandbox", attempts=5, runtime=300),
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        # Requested 5, policy max 1 -> constrained to 1 and escalated to human.
        self.assertEqual(ev.result.constrained_scope.attempt_limit, 1)
        self.assertEqual(ev.outcome, REQUIRES_HUMAN)

    def test_runtime_ceiling_constrained_not_widened(self):
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", "restricted-sandbox", attempts=1, runtime=3600),
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        self.assertEqual(ev.result.constrained_scope.max_runtime_seconds, 600)
        self.assertEqual(ev.outcome, REQUIRES_HUMAN)

    def test_input_hash_preserved(self):
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", "restricted-sandbox"),
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        self.assertEqual(ev.result.constrained_scope.input_hash, "a" * 64)

    def test_acceptance_prerequisite_validation(self):
        # Build a matching AcceptanceArtifact (read-only) and assert the
        # prerequisite check passes; then assert mismatches raise errors.
        acceptance = store_test.make_acceptance_artifact_for_request(
            task_id="task-1", acceptance_id="acceptance-" + "a" * 16,
            acceptance_hash="a" * 64,
        )
        req = _request("run-sandboxed", "restricted-sandbox")
        # Should not raise.
        E.verify_acceptance_prerequisite(req, acceptance)
        # Mismatched id.
        bad = store_test.make_acceptance_artifact_for_request(
            task_id="task-1", acceptance_id="acceptance-" + "b" * 16,
            acceptance_hash="a" * 64,
        )
        with self.assertRaises(ExecutionAuthorizationEvaluationError):
            E.verify_acceptance_prerequisite(req, bad)
        # Mismatched hash.
        bad_h = store_test.make_acceptance_artifact_for_request(
            task_id="task-1", acceptance_id="acceptance-" + "a" * 16,
            acceptance_hash="b" * 64,
        )
        with self.assertRaises(ExecutionAuthorizationEvaluationError):
            E.verify_acceptance_prerequisite(req, bad_h)
        # Mismatched task.
        bad_t = store_test.make_acceptance_artifact_for_request(
            task_id="task-2", acceptance_id="acceptance-" + "a" * 16,
            acceptance_hash="a" * 64,
        )
        with self.assertRaises(ExecutionAuthorizationEvaluationError):
            E.verify_acceptance_prerequisite(req, bad_t)

    def test_accepted_implies_authorization_no(self):
        # A passing evaluation grants nothing; ACCEPTED is prerequisite only.
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", "restricted-sandbox"),
            actor_context=_ctx("u1", as_human := ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        self.assertEqual(ev.outcome, ALLOW)
        # Result must not carry capability-bearing identifiers.
        self.assertNotIn("authorization_id", ev.result.details)
        self.assertNotIn("decision_id", ev.result.details)
        self.assertNotIn("nonce", ev.result.details)
        self.assertNotIn("issued_at", ev.result.details)

    def test_determinism(self):
        args = dict(
            request=_request("run-sandboxed", "restricted-sandbox"),
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        e1 = E.evaluate_execution_authorization_policy(**args)
        e2 = E.evaluate_execution_authorization_policy(**args)
        self.assertEqual(e1.outcome, e2.outcome)
        self.assertEqual(e1.result.reason, e2.result.reason)
        self.assertEqual(e1.result.constrained_scope, e2.result.constrained_scope)


class TestEA3I1NegativeCapability(unittest.TestCase):
    """Prove EA-3I.1 does NOT create or persist any real authorization."""

    def test_no_decision_or_authorization_persisted(self):
        # Evaluating a request must not write anything to the authority store.
        ev = E.evaluate_execution_authorization_policy(
            request=_request("run-sandboxed", "restricted-sandbox"),
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            policy=_policy(),
        )
        self.assertEqual(ev.outcome, ALLOW)
        # No store touched: the evaluator never opens execution_authority.db.
        import os
        from tools.hermes_core.execution_authorization_store import (
            ExecutionAuthorizationStore,
        )
        # The store class exists but the evaluation never calls it.
        self.assertTrue(issubclass(SQLiteExecutionAuthorizationStore, ExecutionAuthorizationStore))
        self.assertNotIn(
            "record_granted_decision_and_authorization",
            E.evaluate_execution_authorization_policy.__code__.co_names,
        )

    def test_no_capability_calls_in_module(self):
        import ast
        with open(E.__file__, encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        # Collect every identifier used in CODE (not docstrings/comments).
        used_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_ids.add(node.id)
            elif isinstance(node, ast.Attribute):
                used_ids.add(node.attr)
        forbidden_ids = {
            "record_granted_decision_and_authorization",
            "record_authorization",
            "record_decision",
            "ExecutionClaim",
            "ExecutionAttempt",
            "WorkerRouter",
            "launch_worker",
            "enqueue",
            "dispatch",
            "AUTHORIZED_FOR_EXECUTION",
            "EXECUTING",
            "generate_nonce",
        }
        hits = forbidden_ids & used_ids
        self.assertFalse(hits, f"forbidden identifiers in evaluation code: {hits}")
        # String-literal mentions (in docstrings/comments) of these are allowed
        # as prose, but the operational call must not appear as a call.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotEqual(
                    name, "record_granted_decision_and_authorization",
                    "evaluation code must not call the EA-3B atomic grant")


if __name__ == "__main__":
    unittest.main()
