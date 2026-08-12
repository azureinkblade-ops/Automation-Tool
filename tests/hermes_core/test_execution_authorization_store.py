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
             expires_at="2026-08-12T22:00:00Z", nonce="nonce-1")
    k.update(o)
    return build_execution_authorization(**k)


def make_req(**o):
    k = dict(task_id="task-1", accepted_governance_artifact_id=VALID_ID,
             accepted_governance_hash=VALID_HASH, requested_scope=make_scope(),
             requesting_actor=make_actor(), authorization_policy=make_policy(),
             requested_at="2026-08-12T21:25:00Z", request_reason="need exec")
    k.update(o)
    return build_execution_authorization_request(**k)


def make_dec(**o):
    k = dict(request_id="execution-authorization-request-" + "c" * 16, task_id="task-1",
             decision_actor=make_actor(),
             outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
             decision_reason="approved", authorization_id="execution-authorization-" + "d" * 16,
             authorization_policy=make_policy())
    k.update(o)
    return build_execution_authorization_decision(**k)


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
        dec = make_dec()
        store.record_decision(dec)
        got = store.get_decision(dec.decision_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.outcome, ExecutionAuthorizationDecisionOutcome.GRANTED)
        self.assertEqual(got.authorization_id, dec.authorization_id)

    def test_record_and_get_authorization(self):
        store = get_execution_authorization_store()
        auth = make_auth()
        store.record_authorization(auth)
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
        auth = make_auth()
        store.record_authorization(auth)
        store.record_authorization(auth)  # no-op, no error
        self.assertEqual(len(store.get_authority_events()), 1)

    def test_conflicting_immutable_fails_closed(self):
        import sqlite3

        store = get_execution_authorization_store()
        auth = make_auth()
        store.record_authorization(auth)
        # Simulate a conflicting immutable record: same artifact id but a different
        # canonical payload already persisted. Re-recording the original must be
        # rejected as a conflict (never silently overwritten).
        conn = sqlite3.connect(store._db_path)
        conn.execute(
            "UPDATE execution_authorizations SET canonical_payload = "
            "replace(canonical_payload, 'stage2-v1-gpu-execution', 'OTHER-OP')"
        )
        conn.commit()
        conn.close()
        with self.assertRaises(ExecutionAuthorizationConflictError):
            store.record_authorization(auth)


class TestStoreReload(unittest.TestCase):
    def test_restart_reload_proof(self):
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "ea.db")
        # First process: persist + close.
        s1 = SQLiteExecutionAuthorizationStore(db)
        auth = make_auth()
        req = make_req()
        dec = make_dec()
        s1.record_authorization(auth)
        s1.record_request(req)
        s1.record_decision(dec)
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
        s.record_authorization(make_auth())
        s.record_request(make_req())
        s.record_decision(make_dec())
        s.close()

    def _conn(self):
        return sqlite3.connect(self.db)

    def test_artifact_payload_tamper_detected(self):
        auth_id = make_auth().authorization_id
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
        auth_id = make_auth().authorization_id
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

    def test_default_version_is_one(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        self.assertTrue(store.verify_integrity().ok)
        store.close()

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


if __name__ == "__main__":
    unittest.main()
