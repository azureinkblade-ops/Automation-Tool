"""EA-2 execution-authority persistence + integrity tests.

These tests use temporary SQLite databases only; they never touch the
production execution_authority.db. Mirrors the governance runtime test seams
(tempfile.mkdtemp + set_execution_authority_db_path_override +
reset_execution_authorization_store_cache).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from tools.hermes_core.execution_authorization import (
    ExecutionAuthorization,
    ExecutionAuthorizationActor,
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationDecision,
    ExecutionAuthorizationDecisionOutcome,
    ExecutionAuthorizationPolicyRef,
    ExecutionAuthorizationRequest,
    ExecutionAuthorizationScope,
    build_execution_authorization,
    build_execution_authorization_decision,
    build_execution_authorization_request,
)
from tools.hermes_core.execution_authorization_store import (
    ExecutionAuthorizationConflictError,
    ExecutionAuthorizationIntegrityError,
    ExecutionAuthorizationSchemaError,
    ExecutionAuthorizationStoreError,
    ExecutionAuthorityLedgerEntry,
)
from tools.hermes_core.runtime import (
    close_execution_authorization_store,
    get_execution_authorization_store,
    reset_execution_authorization_store_cache,
    set_execution_authority_db_path_override,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SCHEMA_VERSION,
    SQLiteExecutionAuthorizationStore,
)

VALID_HASH = "f" * 64
VALID_ID = "acceptance-" + "b" * 16


def make_scope(**o):
    d = dict(operation="stage2-v1-gpu-execution", worker_class="OpenInterpreterWorker",
             input_hash="a" * 64, attempt_limit=1, max_runtime_seconds=300)
    d.update(o)
    return ExecutionAuthorizationScope(**d)


def make_actor(**o):
    d = dict(actor_id="human-owner", actor_type=ExecutionAuthorizationActorType.HUMAN,
             authority_role="owner", authentication_context=None)
    d.update(o)
    return ExecutionAuthorizationActor(**d)


def make_policy(**o):
    d = dict(policy_id="ea-policy", policy_version="1.0")
    d.update(o)
    return ExecutionAuthorizationPolicyRef(**d)


def make_auth(**o):
    k = dict(task_id="task-1", accepted_governance_artifact_id=VALID_ID,
             accepted_governance_hash=VALID_HASH, authorization_actor=make_actor(),
             authorized_scope=make_scope(), authorization_reason="approved",
             authorization_policy=make_policy(), issued_at="2026-08-12T21:30:00Z",
             expires_at="2026-08-12T22:00:00Z", nonce="nonce-1",
             request_id="execution-authorization-request-" + "c" * 16,
             request_hash="c" * 64,
             decision_id="execution-authorization-decision-" + "d" * 16,
             decision_hash="d" * 64)
    k.update(o)
    return build_execution_authorization(**k)


def make_req(**o):
    k = dict(task_id="task-1", accepted_governance_artifact_id=VALID_ID,
             accepted_governance_hash=VALID_HASH, requested_scope=make_scope(),
             requesting_actor=make_actor(), authorization_policy=make_policy(),
             requested_at="2026-08-12T21:25:00Z", request_reason="need exec")
    k.update(o)
    return build_execution_authorization_request(**k)


def make_acceptance_artifact_for_request(task_id, acceptance_id, acceptance_hash):
    """Build an in-memory ACCEPTED AcceptanceArtifact.

    ``acceptance_sha256`` is set to the caller-supplied ``acceptance_hash`` so
    EA-3I.1 prerequisite tests can control exact/mismatched bindings. This
    artifact is NOT persisted to the governance store (which would re-verify the
    hash); EA-3I.2 issuance tests use ``make_persisted_acceptance`` instead.
    """
    from tools.hermes_core.acceptance_artifact import AcceptanceArtifact
    from tools.hermes_core.consensus_disposition import DISPOSITION_ACCEPTED
    return AcceptanceArtifact(
        acceptance_id=acceptance_id,
        task_id=task_id,
        evidence_package_id="evidence-" + "a" * 16,
        consensus_id="consensus-" + "a" * 16,
        finding_set_sha256=acceptance_hash,
        evaluation_sha256=acceptance_hash,
        disposition_sha256=acceptance_hash,
        disposition=DISPOSITION_ACCEPTED,
        reason_codes=("accepted",),
        relevant_finding_keys=(),
        blocking_finding_keys=(),
        blocking_severities=(),
        review_ids=(),
        finding_keys=(),
        accepted_at="2026-08-12T21:00:00Z",
        authority={},
        acceptance_sha256=acceptance_hash,
    )


def make_persisted_acceptance(task_id, acceptance_id):
    """Build an AcceptanceArtifact whose acceptance_sha256 is derived from the
    canonical document shape (matching the governance store's re-verification),
    so it can be persisted via ``record_acceptance`` and later read back through
    ``load_task_governance_chain(...).acceptance``.
    """
    from tools.hermes_core.acceptance_artifact import AcceptanceArtifact
    from tools.hermes_core.consensus_disposition import DISPOSITION_ACCEPTED
    from tools.hermes_core.hashing import sha256_payload
    from tools.hermes_core.acceptance_artifact import _acceptance_document

    base = AcceptanceArtifact(
        acceptance_id=acceptance_id,
        task_id=task_id,
        evidence_package_id="evidence-" + "a" * 16,
        consensus_id="consensus-" + "a" * 16,
        finding_set_sha256="a" * 64,
        evaluation_sha256="a" * 64,
        disposition_sha256="a" * 64,
        disposition=DISPOSITION_ACCEPTED,
        reason_codes=("accepted",),
        relevant_finding_keys=(),
        blocking_finding_keys=(),
        blocking_severities=(),
        review_ids=(),
        finding_keys=(),
        accepted_at="2026-08-12T21:00:00Z",
        authority={},
        acceptance_sha256="",
    )
    derived = sha256_payload(_acceptance_document(base))
    return base.__class__(**{
        **{f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()},
        # Only acceptance_sha256 is derived; the other *_sha256 fields remain as
        # bound hash strings (they are not part of the acceptance identity hash
        # recomputation beyond their literal inclusion, which is unchanged).
        "acceptance_sha256": derived,
    })


def make_dec(**o):
    k = dict(request_id="execution-authorization-request-" + "c" * 16,
             request_hash="c" * 64, task_id="task-1",
             decision_actor=make_actor(),
             outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
             decision_reason="approved", authorization_id="execution-authorization-" + "d" * 16,
             authorization_policy=make_policy())
    k.update(o)
    return build_execution_authorization_decision(**k)


def make_grant_pair(**o):
    """Build a mutually consistent (request, GRANTED decision, authorization)
    triple suitable for record_granted_decision_and_authorization.

    The decision's authorization_id is aligned to the (derived) authorization
    id, and the authorization's decision_hash is aligned to the decision's
    artifact_hash. Because authorization_id is excluded from the decision hash
    preimage (EA-3A Model A), aligning authorization_id leaves the decision's
    decision_id/artifact_hash stable.
    """
    req = make_req()
    dec = build_execution_authorization_decision(
        request_id=req.request_id,
        request_hash=req.artifact_hash,
        task_id=req.task_id,
        decision_actor=make_actor(),
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason="approved",
        authorization_id="execution-authorization-" + "d" * 16,
        authorization_policy=req.authorization_policy,
    )
    auth = build_execution_authorization(
        task_id=req.task_id,
        accepted_governance_artifact_id=req.accepted_governance_artifact_id,
        accepted_governance_hash=req.accepted_governance_hash,
        authorization_actor=make_actor(),
        authorized_scope=make_scope(),
        authorization_reason="approved",
        authorization_policy=req.authorization_policy,
        issued_at="2026-08-12T21:30:00Z",
        expires_at="2026-08-12T22:00:00Z",
        nonce="nonce-1",
        request_id=req.request_id,
        request_hash=req.artifact_hash,
        decision_id=dec.decision_id,
        decision_hash=dec.artifact_hash,
    )
    # Align the decision's authorization_id to the derived authorization id.
    dec = build_execution_authorization_decision(
        request_id=req.request_id,
        request_hash=req.artifact_hash,
        task_id=req.task_id,
        decision_actor=make_actor(),
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason="approved",
        authorization_id=auth.authorization_id,
        authorization_policy=req.authorization_policy,
    )
    return req, dec, auth


class TestStorePersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ea.db")
        set_execution_authority_db_path_override(self.db)

    def tearDown(self):
        set_execution_authority_db_path_override(None)
        reset_execution_authorization_store_cache()
        close_execution_authorization_store()

    def test_record_and_get_request(self):
        store = get_execution_authorization_store()
        req = make_req()
        store.record_request(req)
        got = store.get_request(req.request_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.request_id, req.request_id)
        self.assertEqual(got.artifact_hash, req.artifact_hash)
        self.assertTrue(got.verify_hash())

    def test_record_and_get_decision(self):
        store = get_execution_authorization_store()
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        got = store.get_decision(dec.decision_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.outcome, ExecutionAuthorizationDecisionOutcome.GRANTED)
        self.assertEqual(got.authorization_id, dec.authorization_id)

    def _persist_granted_and_tamper_linkage(self, new_auth_id):
        """Persist a GRANTED decision + authorization atomically, close, directly
        tamper the persisted authorization_id column, reopen, return (store, decision_id)."""
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "ea.db")
        s = SQLiteExecutionAuthorizationStore(db)
        req, dec, auth = make_grant_pair()
        s.record_request(req)
        s.record_granted_decision_and_authorization(dec, auth)
        s.close()
        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE execution_authorization_decisions SET authorization_id = ? "
            "WHERE artifact_id = ?",
            (new_auth_id, dec.decision_id),
        )
        conn.commit()
        conn.close()
        reopened = SQLiteExecutionAuthorizationStore(db)
        return reopened, dec.decision_id

    def test_granted_linkage_tamper_detected_on_get(self):
        # Direct SQL tamper of authorization_id (GRANTED) must be detected on read.
        store, decision_id = self._persist_granted_and_tamper_linkage(
            "execution-authorization-" + "x" * 16
        )
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            store.get_decision(decision_id)
        store.close()

    def test_granted_linkage_tamper_detected_on_verify_integrity(self):
        store, _ = self._persist_granted_and_tamper_linkage(
            "execution-authorization-" + "x" * 16
        )
        report = store.verify_integrity()
        self.assertFalse(report.ok)
        self.assertTrue(
            any("authorization linkage tamper" in f for f in (report.failures or []))
        )
        store.close()

    def _persist_denied_and_tamper_linkage(self, new_auth_id):
        """Persist a DENIED decision (authorization_id NULL), close, directly
        tamper the persisted column to a valid id, reopen, return (store, id)."""
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "ea.db")
        s = SQLiteExecutionAuthorizationStore(db)
        req = make_req()
        s.record_request(req)
        dec = build_execution_authorization_decision(
            request_id=req.request_id, request_hash=req.artifact_hash,
            task_id=req.task_id, decision_actor=make_actor(),
            outcome=ExecutionAuthorizationDecisionOutcome.DENIED,
            decision_reason="no", authorization_id=None,
            authorization_policy=req.authorization_policy)
        s.record_decision(dec)
        s.close()
        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE execution_authorization_decisions SET authorization_id = ? "
            "WHERE artifact_id = ?",
            (new_auth_id, dec.decision_id),
        )
        conn.commit()
        conn.close()
        reopened = SQLiteExecutionAuthorizationStore(db)
        return reopened, dec.decision_id

    def test_denied_linkage_tamper_detected_on_get(self):
        # DENIED must have authorization_id None; tampering it to a valid id is
        # a violation that must be detected fail-closed.
        store, decision_id = self._persist_denied_and_tamper_linkage(
            "execution-authorization-" + "x" * 16
        )
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            store.get_decision(decision_id)
        store.close()

    def test_denied_linkage_tamper_detected_on_verify_integrity(self):
        store, _ = self._persist_denied_and_tamper_linkage(
            "execution-authorization-" + "x" * 16
        )
        report = store.verify_integrity()
        self.assertFalse(report.ok)
        self.assertTrue(
            any("authorization linkage tamper" in f for f in (report.failures or []))
        )
        store.close()

    def test_record_and_get_authorization(self):
        store = get_execution_authorization_store()
        req, auth_dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(auth_dec, auth)
        got = store.get_authorization(auth.authorization_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.accepted_governance_hash, VALID_HASH)

    def test_get_missing_returns_none(self):
        store = get_execution_authorization_store()
        self.assertIsNone(store.get_request("execution-authorization-request-" + "0" * 16))
        self.assertIsNone(store.get_decision("execution-authorization-decision-" + "0" * 16))
        self.assertIsNone(store.get_authorization("execution-authorization-" + "0" * 16))

    def test_idempotent_duplicate(self):
        store = get_execution_authorization_store()
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        store.record_granted_decision_and_authorization(dec, auth)  # idempotent, no error
        self.assertEqual(len(store.get_authority_events()), 3)

    def test_conflicting_immutable_fails_closed(self):
        import sqlite3

        store = get_execution_authorization_store()
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        # Simulate a conflicting immutable record: same artifact id but a different
        # canonical payload already persisted. Re-granting the original must be
        # rejected as a conflict (never silently overwritten).
        conn = sqlite3.connect(store._db_path)
        conn.execute(
            "UPDATE execution_authorizations SET canonical_payload = "
            "replace(canonical_payload, 'stage2-v1-gpu-execution', 'OTHER-OP')"
        )
        conn.commit()
        conn.close()
        with self.assertRaises(ExecutionAuthorizationConflictError):
            store.record_granted_decision_and_authorization(dec, auth)


class TestStoreReload(unittest.TestCase):
    def test_restart_reload_proof(self):
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "ea.db")
        # First process: persist + close.
        s1 = SQLiteExecutionAuthorizationStore(db)
        req, dec, auth = make_grant_pair()
        s1.record_request(req)
        s1.record_granted_decision_and_authorization(dec, auth)
        self.assertTrue(s1.verify_integrity().ok)
        s1.close()
        # Second process: reopen, reload.
        s2 = SQLiteExecutionAuthorizationStore(db)
        got_auth = s2.get_authorization(auth.authorization_id)
        got_req = s2.get_request(req.request_id)
        got_dec = s2.get_decision(dec.decision_id)
        self.assertIsNotNone(got_auth)
        self.assertEqual(got_auth.artifact_hash, auth.artifact_hash)
        self.assertTrue(got_auth.verify_hash())
        self.assertIsNotNone(got_req)
        self.assertIsNotNone(got_dec)
        self.assertTrue(s2.verify_integrity().ok)
        s2.close()


class TestStoreIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ea.db")
        s = SQLiteExecutionAuthorizationStore(self.db)
        req, self.dec, self.auth = make_grant_pair()
        s.record_request(req)
        s.record_granted_decision_and_authorization(self.dec, self.auth)
        s.close()

    def _conn(self):
        return sqlite3.connect(self.db)

    def test_artifact_payload_tamper_detected(self):
        auth_id = self.auth.authorization_id
        conn = self._conn()
        conn.execute(
            "UPDATE execution_authorizations SET canonical_payload = "
            "replace(canonical_payload, 'stage2-v1-gpu-execution', 'TAMPERED')"
        )
        conn.commit()
        conn.close()
        store = SQLiteExecutionAuthorizationStore(self.db)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            store.get_authorization(auth_id)
        # verify_integrity also flags it
        self.assertFalse(store.verify_integrity().ok)
        store.close()

    def test_artifact_hash_tamper_detected(self):
        auth_id = self.auth.authorization_id
        conn = self._conn()
        conn.execute(
            "UPDATE execution_authorizations SET artifact_hash = '0' * 64"
        )
        conn.commit()
        conn.close()
        store = SQLiteExecutionAuthorizationStore(self.db)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            store.get_authorization(auth_id)
        store.close()

    def test_ledger_previous_hash_tamper_detected(self):
        conn = self._conn()
        conn.execute(
            "UPDATE authority_ledger SET previous_entry_sha256 = 'deadbeef' "
            "WHERE sequence_no = (SELECT MAX(sequence_no) FROM authority_ledger)"
        )
        conn.commit()
        conn.close()
        store = SQLiteExecutionAuthorizationStore(self.db)
        report = store.verify_integrity()
        self.assertFalse(report.ok)
        self.assertTrue(any("chain break" in f for f in report.failures))
        store.close()

    def test_ledger_entry_hash_tamper_detected(self):
        conn = self._conn()
        conn.execute(
            "UPDATE authority_ledger SET entry_sha256 = '0' * 64 "
            "WHERE sequence_no = (SELECT MAX(sequence_no) FROM authority_ledger)"
        )
        conn.commit()
        conn.close()
        store = SQLiteExecutionAuthorizationStore(self.db)
        report = store.verify_integrity()
        self.assertFalse(report.ok)
        self.assertTrue(any("entry hash mismatch" in f for f in report.failures))
        store.close()


class TestSchemaVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ea.db")

    def test_default_version_is_three(self):
        # EA-3B added physical request_id columns (UNIQUE) plus
        # request_linkage_sha256 envelopes to the decisions and authorizations
        # tables; the schema version MUST advance with that physical change.
        store = SQLiteExecutionAuthorizationStore(self.db)
        self.assertEqual(SCHEMA_VERSION, 3)
        self.assertTrue(store.verify_integrity().ok)
        store.close()

    def test_pre_ea3b_v2_schema_fails_closed(self):
        # Opening a pre-EA-3B (EA-3A) schema-version-2 authority DB whose
        # decisions/authorizations tables lack the EA-3B request_id columns
        # must NOT silently migrate or "no such column" at read time. It must
        # fail closed as an unsupported old schema pending a separately
        # authorized migration.
        conn = sqlite3.connect(self.db)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("CREATE TABLE authority_schema_version (version INTEGER)")
        conn.execute("INSERT INTO authority_schema_version (version) VALUES (2)")
        conn.execute(
            """
            CREATE TABLE execution_authorization_decisions (
                artifact_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                authorization_id TEXT,
                decision_linkage_sha256 TEXT NOT NULL,
                canonical_payload TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()
        with self.assertRaises(ExecutionAuthorizationSchemaError):
            SQLiteExecutionAuthorizationStore(self.db)

    def test_pre_ea3a_v1_schema_fails_closed(self):
        # Opening a pre-EA-3A (EA-2) schema-version-1 authority DB whose
        # decisions table lacks the EA-3A columns must NOT silently migrate.
        conn = sqlite3.connect(self.db)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "CREATE TABLE authority_schema_version (version INTEGER)"
        )
        conn.execute(
            "INSERT INTO authority_schema_version (version) VALUES (1)"
        )
        conn.execute(
            """
            CREATE TABLE execution_authorization_decisions (
                artifact_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                canonical_payload TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()
        with self.assertRaises(ExecutionAuthorizationSchemaError):
            SQLiteExecutionAuthorizationStore(self.db)

    def test_unsupported_version_fails_closed(self):
        # Open once to create, then corrupt the version row.
        s = SQLiteExecutionAuthorizationStore(self.db)
        s.close()
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE authority_schema_version SET version = 99")
        conn.commit()
        conn.close()
        with self.assertRaises(Exception):
            SQLiteExecutionAuthorizationStore(self.db)

    def test_journal_mode_delete(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode.lower(), "delete")
        store.close()


class TestRuntimeProvider(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ea.db")
        set_execution_authority_db_path_override(self.db)

    def tearDown(self):
        set_execution_authority_db_path_override(None)
        reset_execution_authorization_store_cache()
        close_execution_authorization_store()

    def test_provider_returns_store_and_persists(self):
        store = get_execution_authorization_store()
        store.record_request(make_req())
        self.assertIsNotNone(store.get_request(make_req().request_id))

    def test_resolver_override_env(self):
        from tools.hermes_core.runtime_config import (
            ExecutionAuthorityRuntimeConfigError,
            resolve_execution_authority_db_path,
        )

        path = resolve_execution_authority_db_path(
            env={"HERMES_EXECUTION_AUTHORITY_DB": self.db}
        )
        self.assertEqual(str(path), os.path.abspath(self.db))
        # relative override rejected
        with self.assertRaises(ExecutionAuthorityRuntimeConfigError):
            resolve_execution_authority_db_path(
                env={"HERMES_EXECUTION_AUTHORITY_DB": "relative/path.db"}
            )

    def test_resolver_no_side_effects(self):
        from tools.hermes_core.runtime_config import resolve_execution_authority_db_path

        # resolver must not create the file or its parent.
        target = os.path.join(self.tmp, "nope", "ea.db")
        p = resolve_execution_authority_db_path(
            env={"HERMES_EXECUTION_AUTHORITY_DB": target}
        )
        self.assertFalse(os.path.exists(target))
        self.assertFalse(os.path.exists(os.path.dirname(target)))


class TestEA3BAtomicGrant(unittest.TestCase):
    """EA-3B atomic grant persistence + request-keyed reads (storage-only)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ea.db")

    def tearDown(self):
        pass

    # -- atomic success -----------------------------------------------------
    def test_atomic_grant_success(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        got_d = store.get_decision_for_request(req.request_id)
        got_a = store.get_authorization_for_request(req.request_id)
        self.assertIsNotNone(got_d)
        self.assertIsNotNone(got_a)
        events = [e.event_type for e in store.get_authority_events()]
        self.assertEqual(events, ["REQUEST_RECORDED", "DECISION_RECORDED",
                                   "AUTHORIZATION_RECORDED"])
        self.assertTrue(store.verify_integrity().ok)
        store.close()

    # -- mismatch matrix (zero writes) --------------------------------------
    def _grant_with(self, decision_overrides=None, authorization_overrides=None):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        if decision_overrides:
            dec = build_execution_authorization_decision(
                request_id=dec.request_id, request_hash=dec.request_hash,
                task_id=dec.task_id, decision_actor=dec.decision_actor,
                outcome=decision_overrides.get("outcome", dec.outcome),
                decision_reason=dec.decision_reason,
                authorization_id=decision_overrides.get(
                    "authorization_id", dec.authorization_id),
                authorization_policy=dec.authorization_policy)
        if authorization_overrides:
            o = authorization_overrides
            auth = build_execution_authorization(
                task_id=o.get("task_id", req.task_id),
                accepted_governance_artifact_id=o.get(
                    "accepted_governance_artifact_id",
                    req.accepted_governance_artifact_id),
                accepted_governance_hash=o.get(
                    "accepted_governance_hash", req.accepted_governance_hash),
                authorization_actor=make_actor(), authorized_scope=make_scope(),
                authorization_reason="approved",
                authorization_policy=o.get(
                    "authorization_policy", req.authorization_policy),
                issued_at="2026-08-12T21:30:00Z", expires_at="2026-08-12T22:00:00Z",
                nonce="nonce-1", request_id=o.get("request_id", req.request_id),
                request_hash=o.get("request_hash", req.artifact_hash),
                decision_id=o.get("decision_id", dec.decision_id),
                decision_hash=o.get("decision_hash", dec.artifact_hash))
            # re-align decision authorization_id to the new derived auth id
            dec = build_execution_authorization_decision(
                request_id=dec.request_id, request_hash=dec.request_hash,
                task_id=dec.task_id, decision_actor=dec.decision_actor,
                outcome=dec.outcome, decision_reason=dec.decision_reason,
                authorization_id=auth.authorization_id,
                authorization_policy=dec.authorization_policy)
        try:
            store.record_granted_decision_and_authorization(dec, auth)
            return True, store
        except ExecutionAuthorizationStoreError:
            return False, store

    def test_mismatch_matrix_fails_closed(self):
        # Each mismatch must be rejected with zero durable writes.
        outcomes = []

        # decision outcome != GRANTED
        ok, store = self._grant_with(decision_overrides={
            "authorization_id": None, "outcome": ExecutionAuthorizationDecisionOutcome.DENIED})
        outcomes.append((not ok))

        # authorization_id mismatch (decision id differs from auth derived id)
        ok, store = self._grant_with(decision_overrides={
            "authorization_id": "execution-authorization-" + "z" * 16})
        outcomes.append((not ok))

        # request_id mismatch
        ok, store = self._grant_with(authorization_overrides={
            "request_id": "execution-authorization-request-" + "z" * 16})
        outcomes.append((not ok))

        # request_hash mismatch
        ok, store = self._grant_with(authorization_overrides={
            "request_hash": "e" * 64})
        outcomes.append((not ok))

        # decision_id mismatch
        ok, store = self._grant_with(authorization_overrides={
            "decision_id": "execution-authorization-decision-" + "e" * 16})
        outcomes.append((not ok))

        # decision_hash mismatch
        ok, store = self._grant_with(authorization_overrides={
            "decision_hash": "e" * 64})
        outcomes.append((not ok))

        # task_id mismatch
        ok, store = self._grant_with(authorization_overrides={
            "task_id": "task-other"})
        outcomes.append((not ok))

        # acceptance_id mismatch
        ok, store = self._grant_with(authorization_overrides={
            "accepted_governance_artifact_id": "acceptance-" + "z" * 16})
        outcomes.append((not ok))

        # acceptance_hash mismatch
        ok, store = self._grant_with(authorization_overrides={
            "accepted_governance_hash": "e" * 64})
        outcomes.append((not ok))

        # policy mismatch
        ok, store = self._grant_with(authorization_overrides={
            "authorization_policy": ExecutionAuthorizationPolicyRef(
                policy_id="other", policy_version="9.9")})
        outcomes.append((not ok))

        self.assertTrue(all(outcomes), f"some mismatches were NOT rejected: {outcomes}")
        store.close()

    def test_mismatch_leaves_zero_writes(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        # Break the authorization request_hash.
        bad_auth = build_execution_authorization(
            task_id=req.task_id,
            accepted_governance_artifact_id=req.accepted_governance_artifact_id,
            accepted_governance_hash=req.accepted_governance_hash,
            authorization_actor=make_actor(), authorized_scope=make_scope(),
            authorization_reason="approved",
            authorization_policy=req.authorization_policy,
            issued_at="2026-08-12T21:30:00Z", expires_at="2026-08-12T22:00:00Z",
            nonce="nonce-1", request_id="execution-authorization-request-" + "z" * 16,
            request_hash="e" * 64, decision_id=dec.decision_id,
            decision_hash=dec.artifact_hash)
        with self.assertRaises(ExecutionAuthorizationStoreError):
            store.record_granted_decision_and_authorization(dec, bad_auth)
        # Only the request persisted; no decision, no authorization.
        self.assertIsNone(store.get_decision_for_request(req.request_id))
        self.assertIsNone(store.get_authorization_for_request(req.request_id))
        self.assertEqual(len(store.get_authority_events()), 1)  # only REQUEST_RECORDED
        store.close()

    # -- missing / wrong request -------------------------------------------
    def test_missing_request_fails_closed(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        # Do NOT record the request.
        with self.assertRaises(ExecutionAuthorizationStoreError):
            store.record_granted_decision_and_authorization(dec, auth)
        self.assertEqual(len(store.get_authority_events()), 0)
        store.close()

    def test_wrong_request_hash_fails_closed(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        # A different request persisted (same id, wrong hash).
        wrong_req = build_execution_authorization_request(
            task_id=req.task_id,
            accepted_governance_artifact_id=req.accepted_governance_artifact_id,
            accepted_governance_hash=req.accepted_governance_hash,
            requested_scope=make_scope(), requesting_actor=make_actor(),
            authorization_policy=req.authorization_policy,
            requested_at="2026-08-12T21:25:00Z", request_reason="need exec")
        # Force a different request hash by tampering the stored request.
        store.record_request(req)
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE execution_authorization_requests SET canonical_payload = "
            "replace(canonical_payload, 'stage2-v1-gpu-execution', 'OTHER-OP')")
        conn.commit(); conn.close()
        with self.assertRaises(ExecutionAuthorizationStoreError):
            store.record_granted_decision_and_authorization(dec, auth)
        store.close()

    # -- denied then grant --------------------------------------------------
    def test_denied_then_grant_blocked(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req = make_req()
        store.record_request(req)
        denied = build_execution_authorization_decision(
            request_id=req.request_id, request_hash=req.artifact_hash,
            task_id=req.task_id, decision_actor=make_actor(),
            outcome=ExecutionAuthorizationDecisionOutcome.DENIED,
            decision_reason="no", authorization_id=None,
            authorization_policy=req.authorization_policy)
        store.record_decision(denied)
        req2, dec, auth = make_grant_pair()
        # Build a grant that targets the SAME request_id as the denied one.
        dec = build_execution_authorization_decision(
            request_id=req.request_id, request_hash=req.artifact_hash,
            task_id=req.task_id, decision_actor=make_actor(),
            outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
            decision_reason="approved",
            authorization_id="execution-authorization-" + "d" * 16,
            authorization_policy=req.authorization_policy)
        auth = build_execution_authorization(
            task_id=req.task_id,
            accepted_governance_artifact_id=req.accepted_governance_artifact_id,
            accepted_governance_hash=req.accepted_governance_hash,
            authorization_actor=make_actor(), authorized_scope=make_scope(),
            authorization_reason="approved",
            authorization_policy=req.authorization_policy,
            issued_at="2026-08-12T21:30:00Z", expires_at="2026-08-12T22:00:00Z",
            nonce="nonce-1", request_id=req.request_id,
            request_hash=req.artifact_hash, decision_id=dec.decision_id,
            decision_hash=dec.artifact_hash)
        dec = build_execution_authorization_decision(
            request_id=req.request_id, request_hash=req.artifact_hash,
            task_id=req.task_id, decision_actor=make_actor(),
            outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
            decision_reason="approved", authorization_id=auth.authorization_id,
            authorization_policy=req.authorization_policy)
        with self.assertRaises(ExecutionAuthorizationConflictError):
            store.record_granted_decision_and_authorization(dec, auth)
        store.close()

    # -- idempotent / conflicting replay ------------------------------------
    def test_duplicate_exact_grant_idempotent(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        before = len(store.get_authority_events())
        store.record_granted_decision_and_authorization(dec, auth)  # idempotent
        self.assertEqual(len(store.get_authority_events()), before)
        store.close()

    def test_conflicting_grant_replay_fails_closed(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        # Different authorization for the same request.
        other_auth = build_execution_authorization(
            task_id=req.task_id,
            accepted_governance_artifact_id=req.accepted_governance_artifact_id,
            accepted_governance_hash=req.accepted_governance_hash,
            authorization_actor=make_actor(), authorized_scope=make_scope(),
            authorization_reason="approved",
            authorization_policy=req.authorization_policy,
            issued_at="2026-08-12T21:30:00Z", expires_at="2026-08-12T22:00:00Z",
            nonce="nonce-2", request_id=req.request_id,
            request_hash=req.artifact_hash, decision_id=dec.decision_id,
            decision_hash=dec.artifact_hash)
        other_dec = build_execution_authorization_decision(
            request_id=req.request_id, request_hash=req.artifact_hash,
            task_id=req.task_id, decision_actor=make_actor(),
            outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
            decision_reason="approved",
            authorization_id=other_auth.authorization_id,
            authorization_policy=req.authorization_policy)
        with self.assertRaises(ExecutionAuthorizationConflictError):
            store.record_granted_decision_and_authorization(other_dec, other_auth)
        store.close()

    # -- request-keyed reads + tamper ---------------------------------------
    def test_request_keyed_read_present_and_missing(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        self.assertIsNotNone(store.get_decision_for_request(req.request_id))
        self.assertIsNotNone(store.get_authorization_for_request(req.request_id))
        # Missing request -> None.
        self.assertIsNone(
            store.get_decision_for_request("execution-authorization-request-" + "0" * 16))
        self.assertIsNone(
            store.get_authorization_for_request("execution-authorization-request-" + "0" * 16))
        store.close()

    def test_request_id_tamper_detected_decision(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        store.close()
        tampered_id = "execution-authorization-request-" + "z" * 16
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE execution_authorization_decisions SET request_id = ? "
            "WHERE artifact_id = ?",
            (tampered_id, dec.decision_id))
        conn.commit(); conn.close()
        reopened = SQLiteExecutionAuthorizationStore(self.db)
        # Reading the row by its tampered physical request_id must fail closed
        # (request-linkage envelope mismatch).
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            reopened.get_decision_for_request(tampered_id)
        self.assertFalse(reopened.verify_integrity().ok)
        reopened.close()

    def test_request_id_tamper_detected_authorization(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        store.close()
        tampered_id = "execution-authorization-request-" + "z" * 16
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE execution_authorizations SET request_id = ? WHERE artifact_id = ?",
            (tampered_id, auth.authorization_id))
        conn.commit(); conn.close()
        reopened = SQLiteExecutionAuthorizationStore(self.db)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            reopened.get_authorization_for_request(tampered_id)
        self.assertFalse(reopened.verify_integrity().ok)
        reopened.close()

    # -- rollback injection seam --------------------------------------------
    def test_rollback_after_decision_leaves_zero_residue(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store._fail_after_decision = True
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            store.record_granted_decision_and_authorization(dec, auth)
        store._fail_after_decision = False
        # Rollback must leave zero residue: no decision, no authorization,
        # no DECISION_RECORDED/AUTHORIZATION_RECORDED ledger events.
        self.assertIsNone(store.get_decision_for_request(req.request_id))
        self.assertIsNone(store.get_authorization_for_request(req.request_id))
        events = store.get_authority_events()
        self.assertEqual([e.event_type for e in events], ["REQUEST_RECORDED"])
        self.assertTrue(store.verify_integrity().ok)
        store.close()

    # -- standalone bypass elimination --------------------------------------
    def test_standalone_granted_decision_rejected(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        with self.assertRaises(ExecutionAuthorizationStoreError):
            store.record_decision(dec)
        store.close()

    def test_standalone_authorization_rejected(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        with self.assertRaises(ExecutionAuthorizationStoreError):
            store.record_authorization(auth)
        store.close()

    def test_denied_standalone_still_works(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req = make_req()
        store.record_request(req)
        denied = build_execution_authorization_decision(
            request_id=req.request_id, request_hash=req.artifact_hash,
            task_id=req.task_id, decision_actor=make_actor(),
            outcome=ExecutionAuthorizationDecisionOutcome.DENIED,
            decision_reason="no", authorization_id=None,
            authorization_policy=req.authorization_policy)
        store.record_decision(denied)
        got = store.get_decision(denied.decision_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.outcome, ExecutionAuthorizationDecisionOutcome.DENIED)
        self.assertTrue(store.verify_integrity().ok)
        store.close()

    # -- orphan detection ---------------------------------------------------
    def test_orphan_detection(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        req, dec, auth = make_grant_pair()
        store.record_request(req)
        store.record_granted_decision_and_authorization(dec, auth)
        store.close()
        # Tamper: drop the authorization row but keep the GRANTED decision.
        conn = sqlite3.connect(self.db)
        conn.execute("DELETE FROM execution_authorizations")
        conn.commit(); conn.close()
        reopened = SQLiteExecutionAuthorizationStore(self.db)
        report = reopened.verify_integrity()
        self.assertFalse(report.ok)
        self.assertTrue(any(
            "orphan GRANTED decision" in f for f in (report.failures or [])))
        reopened.close()

    # -- concurrency --------------------------------------------------------
    def test_concurrent_identical_grant(self):
        # Two store instances, same temp DB, same grant.
        req, dec, auth = make_grant_pair()
        s1 = SQLiteExecutionAuthorizationStore(self.db)
        s1.record_request(req)
        s2 = SQLiteExecutionAuthorizationStore(self.db)
        s1.record_granted_decision_and_authorization(dec, auth)
        # Second call (same idempotent grant) must succeed without duplicates.
        s2.record_granted_decision_and_authorization(dec, auth)
        events = [e.event_type for e in s2.get_authority_events()
                  if e.event_type in ("DECISION_RECORDED", "AUTHORIZATION_RECORDED")]
        self.assertEqual(events, ["DECISION_RECORDED", "AUTHORIZATION_RECORDED"])
        self.assertTrue(s2.verify_integrity().ok)
        s1.close(); s2.close()


if __name__ == "__main__":
    unittest.main()
