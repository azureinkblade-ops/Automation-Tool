"""EA-3I.2 tests: capability-bearing execution-authorization issuance.

Asserts that issuance creates real authority ONLY through the validated flow:
exact acceptance binding, actor auth/authority, deterministic policy resolution,
EA-3I.1 evaluation reuse, ALLOW/DENY/REQUIRES_HUMAN mappings, constrained scope,
clock/expiry/nonce generation, replay idempotency, atomic rollback, and that it
creates NO claim/attempt/worker/execution state.
"""

import tempfile
import os
import unittest

from tools.hermes_core import execution_authorization_issuance as I
from tools.hermes_core.execution_authorization import (
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationDecisionOutcome,
    ExecutionAuthorizationPolicyRef,
    ExecutionAuthorizationScope,
    build_execution_authorization_request,
)
from tools.hermes_core.execution_authorization_evaluation import (
    ExecutionAuthorizationActorContext,
    ExecutionAuthorizationActorAuthenticationError,
    ExecutionAuthorizationActorAuthorityError,
)
from tools.hermes_core.execution_authorization_issuance import (
    ExecutionAuthorizationAcceptanceError,
    ExecutionAuthorizationConflictError,
    ExecutionAuthorizationIssuanceOutcome,
    ExecutionAuthorizationIssuanceResult,
    ExecutionAuthorizationRequestNotFoundError,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_governance_store import SQLiteGovernanceStore
from tools.hermes_core.schemas import load_schema_catalog
from tools.hermes_core.runtime import (
    set_execution_authority_db_path_override,
    close_execution_authorization_store,
    reset_execution_authorization_store_cache,
)

from tests.hermes_core.test_execution_authorization_store import (
    make_actor,
    make_persisted_acceptance,
)

KNOWN_OP = "run-sandboxed"
KNOWN_WC = "restricted-sandbox"
POLICY = ExecutionAuthorizationPolicyRef(policy_id="ea-baseline", policy_version="1.0")


def _ctx(actor_id, actor_type, role, auth=True, ref=None):
    return ExecutionAuthorizationActorContext(
        actor_id=actor_id,
        actor_type=actor_type,
        authority_role=role,
        authentication_evidence_present=auth,
        authentication_reference=ref,
    )


def _known_scope(attempt_limit=1, runtime=300):
    return ExecutionAuthorizationScope(
        operation=KNOWN_OP,
        worker_class=KNOWN_WC,
        input_hash="a" * 64,
        attempt_limit=attempt_limit,
        max_runtime_seconds=runtime,
    )


class _IssuanceHarness(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.gov_tmp = tempfile.mkdtemp()
        self.gov_db = os.path.join(self.gov_tmp, "gov.db")
        self.catalog = load_schema_catalog()
        self.governance = SQLiteGovernanceStore(self.gov_db, self.catalog)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)

    def tearDown(self):
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def _bind(self, task_id, acc_id):
        """Persist a request + matching acceptance, return the request."""
        acc = make_persisted_acceptance(task_id, acc_id)
        self.governance.record_acceptance(acc)
        req = build_execution_authorization_request(
            task_id=task_id,
            accepted_governance_artifact_id=acc_id,
            accepted_governance_hash=acc.acceptance_sha256,
            requested_scope=_known_scope(),
            requesting_actor=make_actor(),
            authorization_policy=POLICY,
            requested_at="2026-08-12T21:25:00Z",
            request_reason="need exec",
        )
        self.store.record_request(req)
        return req


class TestEA3I2HappyPath(_IssuanceHarness):
    def test_human_allow_authorized(self):
        req = self._bind("task-1", "acceptance-" + "a" * 16)
        res = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))
        self.assertEqual(res.evaluation_outcome, ExecutionAuthorizationIssuanceOutcome.AUTHORIZED)
        self.assertIsNotNone(res.authorization_id)
        self.assertIsNotNone(res.decision_id)
        self.assertTrue(res.persisted)
        # Durable evidence present in the store.
        dec = self.store.get_decision_for_request(req.request_id)
        auth = self.store.get_authorization_for_request(req.request_id)
        self.assertIsNotNone(dec)
        self.assertIsNotNone(auth)
        self.assertEqual(dec.outcome, ExecutionAuthorizationDecisionOutcome.GRANTED)
        # Atomic ledger pair.
        self.assertTrue(dec.decision_id)
        self.assertEqual(auth.decision_id, dec.decision_id)
        self.assertEqual(auth.decision_hash, dec.artifact_hash)

    def test_policy_service_requires_human(self):
        req = self._bind("task-2", "acceptance-" + "b" * 16)
        res = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("svc", ExecutionAuthorizationActorType.POLICY_SERVICE, "policy-service"))
        self.assertEqual(res.evaluation_outcome, ExecutionAuthorizationIssuanceOutcome.REQUIRES_HUMAN)
        self.assertIsNone(res.authorization_id)
        self.assertFalse(res.persisted)
        self.assertIsNone(self.store.get_decision_for_request(req.request_id))
        self.assertIsNone(self.store.get_authorization_for_request(req.request_id))

    def test_system_denied(self):
        req = self._bind("task-3", "acceptance-" + "c" * 16)
        res = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("sys", ExecutionAuthorizationActorType.SYSTEM, "system"))
        self.assertEqual(res.evaluation_outcome, ExecutionAuthorizationIssuanceOutcome.DENIED)
        self.assertIsNone(res.authorization_id)
        self.assertTrue(res.persisted)
        dec = self.store.get_decision_for_request(req.request_id)
        self.assertIsNotNone(dec)
        self.assertEqual(dec.outcome, ExecutionAuthorizationDecisionOutcome.DENIED)
        self.assertIsNone(dec.authorization_id)
        self.assertIsNone(self.store.get_authorization_for_request(req.request_id))


class TestEA3I2Errors(_IssuanceHarness):
    def test_unknown_request_error(self):
        with self.assertRaises(ExecutionAuthorizationRequestNotFoundError):
            I.issue_execution_authorization(
                store=self.store, governance_store=self.governance,
                request_id="missing",
                actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))

    def test_unauthenticated_error(self):
        req = self._bind("t", "acceptance-" + "a" * 16)
        with self.assertRaises(ExecutionAuthorizationActorAuthenticationError):
            I.issue_execution_authorization(
                store=self.store, governance_store=self.governance,
                request_id=req.request_id,
                actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator", auth=False))

    def test_unknown_role_error(self):
        # "ghost" is not an allowed role for the baseline policy.
        req = self._bind("t", "acceptance-" + "a" * 16)
        with self.assertRaises(ExecutionAuthorizationActorAuthorityError):
            I.issue_execution_authorization(
                store=self.store, governance_store=self.governance,
                request_id=req.request_id,
                actor_context=_ctx("u3", ExecutionAuthorizationActorType.HUMAN, "ghost"))

    def test_unknown_policy_error(self):
        # Bind request to a non-existent policy; resolution must ERROR.
        acc_id = "acceptance-" + "a" * 16
        acc = make_persisted_acceptance("task-x", acc_id)
        self.governance.record_acceptance(acc)
        req = build_execution_authorization_request(
            task_id="task-x", accepted_governance_artifact_id=acc_id,
            accepted_governance_hash=acc.acceptance_sha256,
            requested_scope=_known_scope(), requesting_actor=make_actor(),
            authorization_policy=ExecutionAuthorizationPolicyRef(policy_id="nope", policy_version="9.9"),
            requested_at="2026-08-12T21:25:00Z", request_reason="x")
        self.store.record_request(req)
        with self.assertRaises(I.ExecutionAuthorizationIssuanceError):
            I.issue_execution_authorization(
                store=self.store, governance_store=self.governance,
                request_id=req.request_id,
                actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))

    def test_unsupported_policy_version_error(self):
        acc_id = "acceptance-" + "a" * 16
        acc = make_persisted_acceptance("task-y", acc_id)
        self.governance.record_acceptance(acc)
        req = build_execution_authorization_request(
            task_id="task-y", accepted_governance_artifact_id=acc_id,
            accepted_governance_hash=acc.acceptance_sha256,
            requested_scope=_known_scope(), requesting_actor=make_actor(),
            authorization_policy=ExecutionAuthorizationPolicyRef(policy_id="ea-baseline", policy_version="9.9"),
            requested_at="2026-08-12T21:25:00Z", request_reason="x")
        self.store.record_request(req)
        with self.assertRaises(I.ExecutionAuthorizationIssuanceError):
            I.issue_execution_authorization(
                store=self.store, governance_store=self.governance,
                request_id=req.request_id,
                actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))


class TestEA3I2AcceptancePrereq(_IssuanceHarness):
    def test_acceptance_id_mismatch_error(self):
        # Request bound to acceptance B; governance holds acceptance A.
        req = self._bind("task-5", "acceptance-" + "b" * 16)
        # Overwrite the persisted acceptance with a DIFFERENT artifact id for
        # the same task (substitution attack).
        self.governance.record_acceptance(make_persisted_acceptance("task-5", "acceptance-" + "a" * 16))
        with self.assertRaises(ExecutionAuthorizationAcceptanceError):
            I.issue_execution_authorization(
                store=self.store, governance_store=self.governance,
                request_id=req.request_id,
                actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))
        self.assertIsNone(self.store.get_decision_for_request(req.request_id))
        self.assertIsNone(self.store.get_authorization_for_request(req.request_id))

    def test_acceptance_not_accepted_error(self):
        # A non-accepted disposition must fail the prerequisite.
        acc_id = "acceptance-" + "a" * 16
        from tools.hermes_core.acceptance_artifact import AcceptanceArtifact
        from tools.hermes_core.consensus_disposition import DISPOSITION_REJECTED
        from tools.hermes_core.hashing import sha256_payload
        from tools.hermes_core.acceptance_artifact import _acceptance_document
        base = AcceptanceArtifact(
            acceptance_id=acc_id, task_id="task-9",
            evidence_package_id="evidence-" + "a" * 16,
            consensus_id="consensus-" + "a" * 16,
            finding_set_sha256="a" * 64, evaluation_sha256="a" * 64,
            disposition_sha256="a" * 64, disposition=DISPOSITION_REJECTED,
            reason_codes=("rejected",), relevant_finding_keys=(),
            blocking_finding_keys=(), blocking_severities=(),
            review_ids=(), finding_keys=(), accepted_at="2026-08-12T21:00:00Z",
            authority={}, acceptance_sha256="")
        derived = sha256_payload(_acceptance_document(base))
        acc = base.__class__(**{
            **{f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()},
            "acceptance_sha256": derived})
        self.governance.record_acceptance(acc)
        req = build_execution_authorization_request(
            task_id="task-9", accepted_governance_artifact_id=acc_id,
            accepted_governance_hash=acc.acceptance_sha256,
            requested_scope=_known_scope(), requesting_actor=make_actor(),
            authorization_policy=POLICY, requested_at="2026-08-12T21:25:00Z",
            request_reason="x")
        self.store.record_request(req)
        with self.assertRaises(ExecutionAuthorizationAcceptanceError):
            I.issue_execution_authorization(
                store=self.store, governance_store=self.governance,
                request_id=req.request_id,
                actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))


class TestEA3I2ConstrainedAndBinding(_IssuanceHarness):
    def _authorized(self, attempt_limit=1, runtime=300):
        acc = make_persisted_acceptance("task-c", "acceptance-" + "a" * 16)
        self.governance.record_acceptance(acc)
        req = build_execution_authorization_request(
            task_id="task-c", accepted_governance_artifact_id="acceptance-" + "a" * 16,
            accepted_governance_hash=acc.acceptance_sha256,
            requested_scope=_known_scope(attempt_limit=attempt_limit, runtime=runtime),
            requesting_actor=make_actor(), authorization_policy=POLICY,
            requested_at="2026-08-12T21:25:00Z", request_reason="x")
        self.store.record_request(req)
        res = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))
        return req, res

    def test_constrained_scope_binding(self):
        # Requested WITHIN policy ceilings (1/300) so the outcome is ALLOW; the
        # authorized scope must match the (unconstrained) requested scope exactly
        # and must never be wider.
        req, _ = self._authorized(attempt_limit=1, runtime=300)
        auth = self.store.get_authorization_for_request(req.request_id)
        self.assertIsNotNone(auth)
        # Authorized scope equals the evaluated/requested scope (no widening).
        self.assertEqual(auth.authorized_scope.attempt_limit, 1)
        self.assertEqual(auth.authorized_scope.max_runtime_seconds, 300)
        # Operation/worker binding matches evaluated scope.
        self.assertEqual(auth.authorized_scope.operation, KNOWN_OP)
        self.assertEqual(auth.authorized_scope.worker_class, KNOWN_WC)
        # Input hash preserved exactly.
        self.assertEqual(auth.authorized_scope.input_hash, "a" * 64)

    def test_constrained_scope_ceiling_escalates(self):
        # Requesting BEYOND the policy ceiling (3/3600) must NOT produce an
        # authorization: the constrained scope differs from requested, so the
        # evaluator escalates ALLOW -> REQUIRES_HUMAN. No Authorization created.
        acc = make_persisted_acceptance("task-ce", "acceptance-" + "a" * 16)
        self.governance.record_acceptance(acc)
        req = build_execution_authorization_request(
            task_id="task-ce", accepted_governance_artifact_id="acceptance-" + "a" * 16,
            accepted_governance_hash=acc.acceptance_sha256,
            requested_scope=_known_scope(attempt_limit=3, runtime=3600),
            requesting_actor=make_actor(), authorization_policy=POLICY,
            requested_at="2026-08-12T21:25:00Z", request_reason="x")
        self.store.record_request(req)
        res = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))
        self.assertEqual(res.evaluation_outcome, ExecutionAuthorizationIssuanceOutcome.REQUIRES_HUMAN)
        self.assertIsNone(res.authorization_id)
        self.assertIsNone(self.store.get_authorization_for_request(req.request_id))

    def test_expiry_non_null_and_ordered(self):
        req, _ = self._authorized()
        auth = self.store.get_authorization_for_request(req.request_id)
        self.assertIsNotNone(auth.expires_at)
        self.assertNotEqual(auth.expires_at, "")
        # expires_at > issued_at (strict).
        from datetime import datetime
        issued = datetime.fromisoformat(auth.issued_at.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(auth.expires_at.replace("Z", "+00:00"))
        self.assertGreater(expires, issued)

    def test_nonce_unique_per_request(self):
        req_a, _ = self._authorized()
        # Build a second request.
        acc2 = make_persisted_acceptance("task-c2", "acceptance-" + "d" * 16)
        self.governance.record_acceptance(acc2)
        req2 = build_execution_authorization_request(
            task_id="task-c2", accepted_governance_artifact_id="acceptance-" + "d" * 16,
            accepted_governance_hash=acc2.acceptance_sha256,
            requested_scope=_known_scope(), requesting_actor=make_actor(),
            authorization_policy=POLICY, requested_at="2026-08-12T21:25:00Z",
            request_reason="x")
        self.store.record_request(req2)
        res2 = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req2.request_id,
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))
        auth_a = self.store.get_authorization_for_request(req_a.request_id)
        auth_b = self.store.get_authorization_for_request(req2.request_id)
        self.assertNotEqual(auth_a.nonce, auth_b.nonce)


class TestEA3I2Replay(_IssuanceHarness):
    def test_exact_replay_idempotent(self):
        req = self._bind("task-r", "acceptance-" + "a" * 16)
        r1 = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))
        r2 = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))
        self.assertEqual(r2.decision_id, r1.decision_id)
        self.assertEqual(r2.authorization_id, r1.authorization_id)
        self.assertEqual(r2.authorization_hash, r1.authorization_hash)
        # No new ledger events / duplicate authority.
        auths = []
        cur = self.store._conn.execute(
            "SELECT artifact_id FROM execution_authorizations WHERE request_id = ?",
            (req.request_id,)).fetchall()
        self.assertEqual(len(cur), 1)

    def test_replay_after_denied_never_authorizes(self):
        req = self._bind("task-rd", "acceptance-" + "a" * 16)
        r1 = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("sys", ExecutionAuthorizationActorType.SYSTEM, "system"))
        self.assertEqual(r1.evaluation_outcome, ExecutionAuthorizationIssuanceOutcome.DENIED)
        r2 = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("sys", ExecutionAuthorizationActorType.SYSTEM, "system"))
        self.assertEqual(r2.evaluation_outcome, ExecutionAuthorizationIssuanceOutcome.DENIED)
        self.assertIsNone(self.store.get_authorization_for_request(req.request_id))

    def test_actor_substitution_after_terminal_returns_existing(self):
        # Issue as HUMAN (ALLOW -> AUTHORIZED). Then a different actor calls
        # again; the existing terminal result is returned, no re-decision.
        req = self._bind("task-as", "acceptance-" + "a" * 16)
        r1 = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))
        r2 = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("u9", ExecutionAuthorizationActorType.HUMAN, "execution-admin"))
        self.assertEqual(r2.decision_id, r1.decision_id)
        self.assertEqual(r2.authorization_id, r1.authorization_id)


class TestEA3I2ClockAndRollback(_IssuanceHarness):
    def test_clock_failure_fails_closed(self):
        req = self._bind("task-clk", "acceptance-" + "a" * 16)
        def bad_clock():
            raise RuntimeError("clock unavailable")
        with self.assertRaises(I.ExecutionAuthorizationClockError):
            I.issue_execution_authorization(
                store=self.store, governance_store=self.governance,
                request_id=req.request_id,
                actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
                clock=bad_clock)
        self.assertIsNone(self.store.get_decision_for_request(req.request_id))
        self.assertIsNone(self.store.get_authorization_for_request(req.request_id))

    def test_deterministic_clock(self):
        req = self._bind("task-clk2", "acceptance-" + "a" * 16)
        fixed = "2026-08-13T00:00:00Z"
        r1 = I.issue_execution_authorization(
            store=self.store, governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"),
            clock=lambda: fixed)
        auth = self.store.get_authorization_for_request(req.request_id)
        self.assertEqual(auth.issued_at, fixed)
        self.assertTrue(auth.expires_at.endswith("Z"))

    def test_atomic_rollback_leaves_zero_residue(self):
        # Inject EA-3B failure after Decision write but before Authorization.
        req = self._bind("task-rb", "acceptance-" + "a" * 16)
        self.store._fail_after_decision = True
        try:
            with self.assertRaises(Exception):
                I.issue_execution_authorization(
                    store=self.store, governance_store=self.governance,
                    request_id=req.request_id,
                    actor_context=_ctx("u1", ExecutionAuthorizationActorType.HUMAN, "operator"))
        finally:
            self.store._fail_after_decision = False
        # No decision residue, no authorization residue, no grant ledger residue.
        self.assertIsNone(self.store.get_decision_for_request(req.request_id))
        self.assertIsNone(self.store.get_authorization_for_request(req.request_id))
        cur = self.store._conn.execute(
            "SELECT COUNT(*) AS n FROM authority_ledger WHERE event_type IN "
            "('DECISION_RECORDED','AUTHORIZATION_RECORDED')").fetchone()
        self.assertEqual(cur["n"], 0)


class TestEA3I2NoExecutionBoundary(_IssuanceHarness):
    def test_no_claim_worker_execution_artifacts(self):
        import ast
        with open(I.__file__, encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
        # Execution-boundary tokens are forbidden in EA-3I.2 (claim/attempt/
        # worker/execution-state). Persistence via the safe EA-3B APIs
        # (record_decision for DENY, record_granted_decision_and_authorization
        # for ALLOW) is explicitly authorized in this module only.
        forbidden = {
            "ExecutionClaim", "ExecutionAttempt", "WorkerRouter", "launch_worker",
            "enqueue", "dispatch", "AUTHORIZED_FOR_EXECUTION", "EXECUTION_CLAIMED",
            "EXECUTING", "claim_expires_at", "claimed_at", "claim_id",
            "execution_attempt_id",
        }
        hits = forbidden & used
        self.assertFalse(hits, f"forbidden execution-boundary tokens: {hits}")
        # Authorized persistence MUST go only through safe EA-3B APIs; the
        # standalone Authorization persistence path must not appear.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotEqual(name, "record_authorization")



if __name__ == "__main__":
    unittest.main()
