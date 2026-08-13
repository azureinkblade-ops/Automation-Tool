"""EA-4A tests: ExecutionClaim domain + atomic claim persistence.

Asserts that a durable ExecutionClaim is created ONLY through the validated
flow: authorization exists + integrity + unexpired at claim time, bounded
non-null claim lifetime, one active claim per authorization, exact replay
idempotency, conflicting-claimant CONFLICT, tamper/orphan detection, and that
NO claim/attempt/worker/execution state is created. The CLAIM_RECORDED ledger
event is emitted exactly once and rollback leaves zero residue.
"""

import tempfile
import os
import unittest

from tools.hermes_core import execution_authorization_claim as C
from tools.hermes_core import execution_authorization_issuance as I
from tools.hermes_core.execution_authorization import (
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationPolicyRef,
    ExecutionAuthorizationScope,
    ExecutionClaimant,
    build_execution_authorization_request,
)
from tools.hermes_core.execution_authorization_evaluation import (
    ExecutionAuthorizationActorContext,
)
from tools.hermes_core.execution_authorization_claim import (
    ExecutionAuthorizationClaimConflictError,
    ExecutionAuthorizationClaimError,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    ExecutionAuthorizationIntegrityError,
    ExecutionAuthorizationSchemaError,
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

POLICY = ExecutionAuthorizationPolicyRef(policy_id="ea-baseline", policy_version="1.0")
CLAIMANT_A = ExecutionClaimant(
    claimant_id="worker-manager", claimant_type="worker-manager", claimant_context="node-1"
)
CLAIMANT_B = ExecutionClaimant(claimant_id="scheduler", claimant_type="scheduler")


def _ctx(actor_id="u1", actor_type=ExecutionAuthorizationActorType.HUMAN, role="operator"):
    return ExecutionAuthorizationActorContext(
        actor_id=actor_id,
        actor_type=actor_type,
        authority_role=role,
        authentication_evidence_present=True,
    )


def _known_scope(attempt_limit=1, runtime=300):
    return ExecutionAuthorizationScope(
        operation="run-sandboxed",
        worker_class="restricted-sandbox",
        input_hash="a" * 64,
        attempt_limit=attempt_limit,
        max_runtime_seconds=runtime,
    )


class _ClaimHarness(unittest.TestCase):
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

    def _bind_and_issue(self, task_id, acc_id, expires_at="2026-08-12T22:00:00Z"):
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
        res = I.issue_execution_authorization(
            store=self.store,
            governance_store=self.governance,
            request_id=req.request_id,
            actor_context=_ctx(),
        )
        return self.store.get_authorization_for_request(req.request_id)


class TestEA4AClaimHappyPath(_ClaimHarness):
    def test_happy_claim_persisted(self):
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        result = C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        self.assertTrue(result.persisted)
        self.assertFalse(result.replayed)
        self.assertIsNotNone(result.claim_id)
        claim = self.store.get_claim(result.claim_id)
        self.assertIsNotNone(claim)
        # Exactly one CLAIM_RECORDED ledger event.
        events = [e for e in self.store.get_authority_events()
                  if e.event_type == "CLAIM_RECORDED"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].artifact_id, result.claim_id)
        # Cryptographic lineage binds to exact Authorization/Request/Decision.
        self.assertEqual(claim.authorization_id, auth.authorization_id)
        self.assertEqual(claim.authorization_hash, auth.artifact_hash)
        self.assertEqual(claim.request_id, auth.request_id)
        self.assertEqual(claim.request_hash, auth.request_hash)
        self.assertEqual(claim.decision_id, auth.decision_id)
        self.assertEqual(claim.decision_hash, auth.decision_hash)
        self.assertEqual(claim.task_id, auth.task_id)
        self.assertTrue(claim.verify_hash())

    def test_claim_time_semantics(self):
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        result = C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        self.assertTrue(result.claim_expires_at.endswith("Z"))
        self.assertTrue(result.claimed_at.endswith("Z"))
        # claim_expires_at > claimed_at and non-null.
        self.assertIsNotNone(result.claim_expires_at)
        from datetime import datetime, timezone
        claimed = datetime.fromisoformat(result.claimed_at.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(result.claim_expires_at.replace("Z", "+00:00"))
        self.assertGreater(expires, claimed)

    def test_claim_lifetime_bounded(self):
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        result = C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        from datetime import datetime, timezone
        claimed = datetime.fromisoformat(result.claimed_at.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(result.claim_expires_at.replace("Z", "+00:00"))
        delta = (expires - claimed).total_seconds()
        self.assertLessEqual(delta, 300)
        self.assertGreater(delta, 0)


class TestEA4AClaimPrerequisites(_ClaimHarness):
    def test_missing_authorization_error(self):
        with self.assertRaises(ExecutionAuthorizationClaimError):
            C.claim_execution_authorization(
                store=self.store,
                authorization_id="execution-authorization-" + "0" * 16,
                claimant=CLAIMANT_A,
            )

    def test_expired_authorization_blocked(self):
        from datetime import datetime, timedelta, timezone
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        # Clock strictly after the Authorization's actual expiry.
        exp = datetime.fromisoformat(auth.expires_at.replace("Z", "+00:00"))
        late = (exp + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        with self.assertRaises(ExecutionAuthorizationClaimError):
            C.claim_execution_authorization(
                store=self.store,
                authorization_id=auth.authorization_id,
                claimant=CLAIMANT_A,
                clock=lambda: late,
            )

    def test_boundary_expiry_blocked(self):
        # Authorization expires exactly at claim time -> blocked (no grace).
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        boundary = auth.expires_at  # exactly equal -> blocked
        with self.assertRaises(ExecutionAuthorizationClaimError):
            C.claim_execution_authorization(
                store=self.store,
                authorization_id=auth.authorization_id,
                claimant=CLAIMANT_A,
                clock=lambda: boundary,
            )


class TestEA4AClaimReplayAndConflict(_ClaimHarness):
    def test_exact_replay_idempotent(self):
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        r1 = C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        r2 = C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        self.assertEqual(r1.claim_id, r2.claim_id)
        self.assertEqual(r1.claimed_at, r2.claimed_at)
        self.assertEqual(r1.claim_expires_at, r2.claim_expires_at)
        self.assertTrue(r2.replayed)
        self.assertTrue(r2.persisted)
        # Single ledger event.
        events = [e for e in self.store.get_authority_events()
                  if e.event_type == "CLAIM_RECORDED"]
        self.assertEqual(len(events), 1)

    def test_conflicting_claimant_rejected(self):
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        with self.assertRaises(ExecutionAuthorizationClaimConflictError):
            C.claim_execution_authorization(
                store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_B
            )
        # Existing claim unmodified.
        claim = self.store.get_claim_for_authorization(auth.authorization_id)
        self.assertEqual(claim.claimant.claimant_id, "worker-manager")


class TestEA4AClaimIntegrity(_ClaimHarness):
    def test_claim_hash_linkage_tamper_detected(self):
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        # Tamper the physical authorization_hash binding column.
        self.store._conn.execute(
            "UPDATE execution_authorization_claims SET authorization_hash = ? "
            "WHERE authorization_id = ?",
            ("f" * 64, auth.authorization_id),
        )
        self.store._conn.commit()
        rep = self.store.verify_integrity()
        self.assertFalse(rep.ok)
        self.assertTrue(any("linkage tamper" in f for f in rep.failures))

    def test_orphan_claim_detected(self):
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        # Remove the backing Authorization -> orphan claim.
        self.store._conn.execute(
            "DELETE FROM execution_authorizations WHERE artifact_id = ?",
            (auth.authorization_id,),
        )
        self.store._conn.commit()
        rep = self.store.verify_integrity()
        self.assertFalse(rep.ok)
        self.assertTrue(any("orphan" in f for f in rep.failures))

    def test_store_rejects_authorization_linkage_mismatch(self):
        # Store-level: a Claim whose authorization_hash/request_hash/decision
        # linkage does not match the persisted Authorization must be rejected.
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        from tools.hermes_core.execution_authorization import build_execution_claim

        tampered = build_execution_claim(
            authorization_id=auth.authorization_id,
            authorization_hash="f" * 64,  # wrong hash
            request_id=auth.request_id,
            request_hash=auth.request_hash,
            decision_id=auth.decision_id,
            decision_hash=auth.decision_hash,
            task_id=auth.task_id,
            claimant=CLAIMANT_A,
            claimed_at="2026-08-12T21:26:00Z",
            claim_expires_at="2026-08-12T21:31:00Z",
            authorization_policy=auth.authorization_policy,
            claim_reason="mismatch",
        )
        with self.assertRaises(Exception):
            self.store.claim_authorization_atomically(auth.authorization_id, tampered)

    def test_multiple_claims_detected(self):
        # Direct tamper: rebuild the claims table without the UNIQUE constraint
        # so a second claim row for the same authorization can be inserted,
        # then verify the integrity check detects the multiplicity.
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        conn = self.store._conn
        conn.execute(
            "ALTER TABLE execution_authorization_claims RENAME TO c_tmp"
        )
        conn.execute(
            "CREATE TABLE execution_authorization_claims ("
            "artifact_id TEXT PRIMARY KEY, authorization_id TEXT NOT NULL, "
            "authorization_hash TEXT NOT NULL, request_id TEXT NOT NULL, "
            "request_hash TEXT NOT NULL, decision_id TEXT NOT NULL, "
            "decision_hash TEXT NOT NULL, task_id TEXT NOT NULL, "
            "artifact_type TEXT NOT NULL, claimed_at TEXT NOT NULL, "
            "claim_expires_at TEXT NOT NULL, claimant_json TEXT NOT NULL, "
            "artifact_version TEXT NOT NULL, artifact_hash TEXT NOT NULL, "
            "claim_linkage_sha256 TEXT NOT NULL, canonical_payload TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO execution_authorization_claims SELECT * FROM c_tmp"
        )
        conn.execute(
            "INSERT INTO execution_authorization_claims "
            "(artifact_id, authorization_id, authorization_hash, request_id, "
            "request_hash, decision_id, decision_hash, task_id, artifact_type, "
            "claimed_at, claim_expires_at, claimant_json, artifact_version, "
            "artifact_hash, claim_linkage_sha256, canonical_payload) "
            "SELECT 'execution-authorization-claim-' || 'x' || substr(artifact_id, 38), "
            "authorization_id, authorization_hash, request_id, request_hash, "
            "decision_id, decision_hash, task_id, artifact_type, claimed_at, "
            "claim_expires_at, claimant_json, artifact_version, artifact_hash, "
            "claim_linkage_sha256, canonical_payload FROM c_tmp"
        )
        conn.execute("DROP TABLE c_tmp")
        conn.commit()
        rep = self.store.verify_integrity()
        self.assertFalse(rep.ok)
        self.assertTrue(any("claims (at most one" in f for f in rep.failures))


class TestEA4AClaimReadIntegrityTamper(_ClaimHarness):
    """Ordinary Claim reads must fail closed on physical linkage tampering.

    Each test tampers one physical binding column and proves BOTH that
    get_claim(...) raises an integrity error AND verify_integrity().ok is False.
    """

    def _claim_and_tamper(self, column, bad_value):
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        C.claim_execution_authorization(
            store=self.store, authorization_id=auth.authorization_id, claimant=CLAIMANT_A
        )
        claim = self.store.get_claim_for_authorization(auth.authorization_id)
        self.store._conn.execute(
            f"UPDATE execution_authorization_claims SET {column} = ? "
            "WHERE artifact_id = ?",
            (bad_value, claim.claim_id),
        )
        self.store._conn.commit()
        return claim.claim_id

    def _assert_read_fails_closed(self, column, bad_value):
        claim_id = self._claim_and_tamper(column, bad_value)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_claim(claim_id)
        rep = self.store.verify_integrity()
        self.assertFalse(rep.ok)
        self.assertTrue(any("claim linkage tamper" in f for f in rep.failures))

    def test_get_claim_rejects_authorization_id_tamper(self):
        self._assert_read_fails_closed("authorization_id", "execution-authorization-" + "0" * 16)

    def test_get_claim_rejects_authorization_hash_tamper(self):
        self._assert_read_fails_closed("authorization_hash", "f" * 64)

    def test_get_claim_rejects_request_id_tamper(self):
        self._assert_read_fails_closed("request_id", "execution-authorization-request-" + "0" * 16)

    def test_get_claim_rejects_request_hash_tamper(self):
        self._assert_read_fails_closed("request_hash", "f" * 64)

    def test_get_claim_rejects_decision_id_tamper(self):
        self._assert_read_fails_closed("decision_id", "execution-authorization-decision-" + "0" * 16)

    def test_get_claim_rejects_decision_hash_tamper(self):
        self._assert_read_fails_closed("decision_hash", "f" * 64)


class TestEA4AClaimRollback(_ClaimHarness):
    def test_atomic_rollback_leaves_zero_residue(self):
        auth = self._bind_and_issue("task-1", "acceptance-" + "a" * 16)
        self.store._fail_after_claim_row = True
        with self.assertRaises(RuntimeError):
            C.claim_execution_authorization(
                store=self.store,
                authorization_id=auth.authorization_id,
                claimant=CLAIMANT_A,
            )
        # Claim absent, CLAIM_RECORDED absent, Authorization remains.
        self.assertIsNone(
            self.store.get_claim_for_authorization(auth.authorization_id)
        )
        events = [e for e in self.store.get_authority_events()
                  if e.event_type == "CLAIM_RECORDED"]
        self.assertEqual(len(events), 0)
        self.assertIsNotNone(self.store.get_authorization(auth.authorization_id))


class TestEA4AClaimBoundary(_ClaimHarness):
    def test_no_claim_worker_execution_artifacts(self):
        # Negative capability scan: claim module must not define or reference
        # execution/worker/attempt behavior as identifiers (docstrings that
        # describe future phases are permitted).
        import inspect
        import ast

        src = inspect.getsource(C)
        tree = ast.parse(src)
        forbidden = {
            "ExecutionAttempt", "WorkerRouter", "launch_worker", "enqueue",
            "dispatch", "subprocess", "EXECUTING", "execution_started",
            "process_id", "worker_pid", "exit_code", "stdout", "stderr",
        }
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.add(node.name)
        hit = forbidden & found
        self.assertEqual(hit, set(), f"forbidden token(s) present: {hit}")
        # Function/class defs must not include worker-launch behavior.
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.assertNotIn("launch", node.name.lower())
                self.assertNotIn("dispatch", node.name.lower())


class TestEA4ASchemaCompatibility(unittest.TestCase):
    """Schema v4 is the only supported authority schema. Old and future
    versions MUST fail closed with no silent migration."""

    def _make_db(self, version):
        import sqlite3

        d = tempfile.mkdtemp()
        p = os.path.join(d, "ea.db")
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS authority_schema_version (version INTEGER)"
        )
        cur.execute(
            "INSERT INTO authority_schema_version (version) VALUES (?)", (version,)
        )
        conn.commit()
        conn.close()
        return p

    def test_fresh_v4_opens(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "ea.db")
        store = SQLiteExecutionAuthorizationStore(p)
        self.assertTrue(store.verify_integrity().ok)
        store.close()

    def test_v3_fails_closed(self):
        p = self._make_db(3)
        with self.assertRaises(ExecutionAuthorizationSchemaError):
            SQLiteExecutionAuthorizationStore(p)

    def test_v2_fails_closed(self):
        p = self._make_db(2)
        with self.assertRaises(ExecutionAuthorizationSchemaError):
            SQLiteExecutionAuthorizationStore(p)

    def test_v1_fails_closed(self):
        p = self._make_db(1)
        with self.assertRaises(ExecutionAuthorizationSchemaError):
            SQLiteExecutionAuthorizationStore(p)

    def test_future_version_fails_closed(self):
        p = self._make_db(99)
        with self.assertRaises(ExecutionAuthorizationSchemaError):
            SQLiteExecutionAuthorizationStore(p)


class TestEA4AClaimConcurrency(_ClaimHarness):
    """Real concurrency proof: two separate connections to the SAME authority
    DB contend to claim one Authorization. BEGIN IMMEDIATE serializes writers,
    but the lost racer must still get a correct domain outcome (not a raw
    sqlite3.IntegrityError): same claimant -> idempotent first-writer-wins;
    different claimant -> CONFLICT.
    """

    def _issue_auth(self):
        return self._bind_and_issue("task-1", "acceptance-" + "a" * 16)

    def _race(self, claimant_a, claimant_b, fixed_clock):
        import threading

        auth = self._issue_auth()
        # Build a SEPARATE store connection INSIDE each worker thread
        # (sqlite3 objects are thread-affine). Both target the same DB file,
        # so this is true cross-connection contention, not in-process
        # serialization.
        results = {}
        lock = threading.Lock()

        def worker(claimant, key):
            store = SQLiteExecutionAuthorizationStore(self.ea_db)
            try:
                r = C.claim_execution_authorization(
                    store=store,
                    authorization_id=auth.authorization_id,
                    claimant=claimant,
                    clock=lambda: fixed_clock,
                )
                with lock:
                    results[key] = ("ok", r)
            except ExecutionAuthorizationClaimConflictError as e:
                with lock:
                    results[key] = ("conflict", str(e))
            except Exception as e:  # noqa: BLE001
                with lock:
                    results[key] = ("error", f"{type(e).__name__}: {e}")
            finally:
                store.close()

        ta = threading.Thread(target=worker, args=(claimant_a, "a"))
        tb = threading.Thread(target=worker, args=(claimant_b, "b"))
        ta.start()
        tb.start()
        ta.join()
        tb.join()
        return auth, results

    def test_concurrent_same_claimant_idempotent(self):
        from datetime import datetime, timezone

        fixed = (datetime(2026, 8, 12, 21, 27, tzinfo=timezone.utc)
                 .isoformat().replace("+00:00", "Z"))
        auth, results = self._race(CLAIMANT_A, CLAIMANT_A, fixed)
        # Both attempts must succeed (idempotent) and agree on one claim.
        self.assertIn(results["a"][0], ("ok",))
        self.assertIn(results["b"][0], ("ok",))
        self.assertEqual(results["a"][1].claim_id, results["b"][1].claim_id)
        # Exactly one durable Claim + one CLAIM_RECORDED event.
        claim = self.store.get_claim_for_authorization(auth.authorization_id)
        self.assertIsNotNone(claim)
        events = [e for e in self.store.get_authority_events()
                  if e.event_type == "CLAIM_RECORDED"]
        self.assertEqual(len(events), 1)
        self.assertTrue(self.store.verify_integrity().ok)

    def test_concurrent_different_claimant_conflict(self):
        from datetime import datetime, timezone

        fixed = (datetime(2026, 8, 12, 21, 27, tzinfo=timezone.utc)
                 .isoformat().replace("+00:00", "Z"))
        auth, results = self._race(CLAIMANT_A, CLAIMANT_B, fixed)
        # Exactly one of the two wins (ok); the other gets CONFLICT, never a
        # raw error. No claimant transfer; the winner's claimant is preserved.
        outcomes = {results["a"][0], results["b"][0]}
        self.assertIn("ok", outcomes)
        self.assertIn("conflict", outcomes)
        self.assertNotIn("error", outcomes)
        claim = self.store.get_claim_for_authorization(auth.authorization_id)
        self.assertIsNotNone(claim)
        # Winner is one of the two claimants; the loser did not overwrite it.
        self.assertIn(claim.claimant.claimant_id, ("worker-manager", "scheduler"))
        events = [e for e in self.store.get_authority_events()
                  if e.event_type == "CLAIM_RECORDED"]
        self.assertEqual(len(events), 1)
        self.assertTrue(self.store.verify_integrity().ok)


if __name__ == "__main__":
    unittest.main()
