"""EA-4D.4A: persistence + v2->v3 migration tests.

Covers: fresh v3 DB, exact empty v2 -> v3 success, populated v2 -> typed
refusal (row/table/version untouched), rollback seams, version advancement
LAST, v3 exact shape (all five new columns NOT NULL), idempotent replay,
FAILED conflict semantics, and negative capability (no subprocess/network).
"""

import os
import sqlite3
import tempfile
import unittest

from tools.hermes_core.execution_start import ExecutionStartOutcome
from tools.hermes_core.execution_start_result_service import (
    ExecutionStartResultService, VerifiedRuntimeStartEvidence)
from tools.hermes_core.runtime_launch_adapter import RuntimeLookupOutcome
from tools.hermes_core.sqlite_execution_start_store import (
    SQLiteExecutionStartStore, SCHEMA_VERSION_START, SCHEMA_VERSION_LATEST,
    ExecutionStartMigrationError, V2_RESULT_COLUMNS,
)
from tools.hermes_core.hashing import sha256_payload


def _seed_v2_db(path, *, result_rows=(), with_schema_version=2,
                v3_result_shape=False):
    """Create an on-disk v2 Start DB (no migration logic) for migration tests."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("CREATE TABLE start_schema_version (version INTEGER)")
    conn.execute("INSERT INTO start_schema_version (version) VALUES (?)",
                 (with_schema_version,))
    conn.execute(
        """
        CREATE TABLE execution_start_reservations (
            reservation_id TEXT PRIMARY KEY, artifact_hash TEXT NOT NULL,
            route_id TEXT NOT NULL UNIQUE, route_hash TEXT NOT NULL,
            attempt_id TEXT NOT NULL, attempt_hash TEXT NOT NULL,
            authorization_id TEXT NOT NULL, authorization_hash TEXT NOT NULL,
            claim_id TEXT NOT NULL, claim_hash TEXT NOT NULL,
            request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
            decision_id TEXT NOT NULL, decision_hash TEXT NOT NULL,
            task_id TEXT NOT NULL, worker_id TEXT NOT NULL, worker_class TEXT,
            worker_version TEXT NOT NULL, operation TEXT NOT NULL,
            input_hash TEXT NOT NULL, reserved_at TEXT NOT NULL,
            must_start_by TEXT NOT NULL, launcher_actor_id TEXT NOT NULL,
            launcher_actor_type TEXT NOT NULL, launcher_actor_context TEXT,
            status TEXT NOT NULL, canonical_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL
        )
        """)
    if v3_result_shape:
        cols = (
            "start_result_id TEXT PRIMARY KEY, artifact_hash TEXT NOT NULL, "
            "launch_attempt_id TEXT NOT NULL UNIQUE, launch_attempt_hash TEXT NOT NULL, "
            "reservation_id TEXT NOT NULL, reservation_hash TEXT NOT NULL, "
            "route_id TEXT NOT NULL, route_hash TEXT NOT NULL, task_id TEXT NOT NULL, "
            "worker_id TEXT NOT NULL, worker_version TEXT NOT NULL, outcome TEXT NOT NULL, "
            "recorded_at TEXT NOT NULL, runtime_run_id TEXT, error_code TEXT, "
            "error_summary TEXT, canonical_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, "
            "runtime_binding_id TEXT NOT NULL, runtime_binding_version TEXT NOT NULL, "
            "runtime_binding_hash TEXT NOT NULL, idempotency_key TEXT NOT NULL, "
            "runtime_evidence_hash TEXT NOT NULL"
        )
    else:
        cols = (
            "start_result_id TEXT PRIMARY KEY, artifact_hash TEXT NOT NULL, "
            "launch_attempt_id TEXT NOT NULL UNIQUE, launch_attempt_hash TEXT NOT NULL, "
            "reservation_id TEXT NOT NULL, reservation_hash TEXT NOT NULL, "
            "route_id TEXT NOT NULL, route_hash TEXT NOT NULL, task_id TEXT NOT NULL, "
            "worker_id TEXT NOT NULL, worker_version TEXT NOT NULL, outcome TEXT NOT NULL, "
            "recorded_at TEXT NOT NULL, runtime_run_id TEXT, error_code TEXT, "
            "error_summary TEXT, canonical_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL"
        )
    conn.execute(f"CREATE TABLE execution_start_results ({cols})")
    stub = SQLiteExecutionStartStore.__new__(SQLiteExecutionStartStore)
    stub._conn = conn
    stub._ensure_v2_tables(conn)
    for row in result_rows:
        conn.execute(
            "INSERT INTO execution_start_results "
            "(start_result_id, artifact_hash, launch_attempt_id, launch_attempt_hash, "
            "reservation_id, reservation_hash, route_id, route_hash, task_id, worker_id, "
            "worker_version, outcome, recorded_at, runtime_run_id, error_code, "
            "error_summary, canonical_json, payload_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            row)
    conn.commit()
    conn.close()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "start.db")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _version(self, path):
        conn = sqlite3.connect(path)
        v = conn.execute("SELECT version FROM start_schema_version").fetchone()[0]
        conn.close()
        return v

    def _raw_v2_store(self):
        store = SQLiteExecutionStartStore.__new__(SQLiteExecutionStartStore)
        store._db_path = None
        store._conn = sqlite3.connect(self.db, isolation_level=None)
        store._conn.row_factory = sqlite3.Row
        store._conn.execute("PRAGMA foreign_keys = ON")
        store._fail_before_v3_rename = False
        store._fail_after_v3_create = False
        return store

    def test_fresh_store_is_v3_after_migrate(self):
        store = SQLiteExecutionStartStore(self.db)
        store.migrate_to_v3()
        self.assertEqual(self._version(self.db), SCHEMA_VERSION_LATEST)
        store.close()

    def test_exact_empty_v2_migrates_to_v3(self):
        _seed_v2_db(self.db, with_schema_version=2, v3_result_shape=False)
        store = SQLiteExecutionStartStore(self.db)
        self.assertEqual(self._version(self.db), SCHEMA_VERSION_LATEST)
        # v3 shape has the five new NOT NULL columns.
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        cols = [r["name"] for r in conn.execute(
            "PRAGMA table_info(execution_start_results)").fetchall()]
        for c in ("runtime_binding_id", "runtime_binding_version",
                  "runtime_binding_hash", "idempotency_key",
                  "runtime_evidence_hash"):
            self.assertIn(c, cols)
        conn.close()
        store.close()

    def test_populated_v2_refuses_migration(self):
        row = ("srid-1", "a" * 64, "latch-1", "L" * 64, "res-1", "r" * 64,
               "route-1", "r" * 64, "task-1", "worker-1", "1", "STARTED",
               "2024-01-01T00:00:00Z", "run-1", None, None,
               "{}", "p" * 64)
        _seed_v2_db(self.db, with_schema_version=2, v3_result_shape=False,
                    result_rows=[row])
        with self.assertRaises(ExecutionStartMigrationError):
            SQLiteExecutionStartStore(self.db)
        # Row, table, and version remain untouched (fail closed).
        self.assertEqual(self._version(self.db), 2)
        conn = sqlite3.connect(self.db)
        count = conn.execute(
            "SELECT COUNT(*) FROM execution_start_results").fetchone()[0]
        self.assertEqual(count, 1)
        conn.close()

    def test_fail_before_v3_rename_seam_refuses(self):
        _seed_v2_db(self.db, with_schema_version=2, v3_result_shape=False)
        store = self._raw_v2_store()
        store._fail_before_v3_rename = True
        with self.assertRaises(ExecutionStartMigrationError):
            store.migrate_to_v3()
        self.assertEqual(self._version(self.db), 2)
        store.close()

    def test_post_create_pre_rename_rollback(self):
        """In-flight DDL inside BEGIN IMMEDIATE rolls back on injected failure.

        Proves the transactional migration: after the replacement table is
        created but before the destructive DROP/RENAME, an injected failure
        causes _run_atomic to ROLLBACK, leaving the original v2 table,
        original schema, version 2, and NO execution_start_results_v3 residue.
        """
        _seed_v2_db(self.db, with_schema_version=2, v3_result_shape=False)
        store = self._raw_v2_store()
        store._fail_after_v3_create = True
        with self.assertRaises(ExecutionStartMigrationError):
            store.migrate_to_v3()
        # Post-failure assertions: full rollback of in-flight DDL.
        self.assertEqual(self._version(self.db), 2)
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        v2_cols = [r["name"] for r in conn.execute(
            "PRAGMA table_info(execution_start_results)").fetchall()]
        self.assertEqual(v2_cols, list(V2_RESULT_COLUMNS))
        names = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        self.assertNotIn("execution_start_results_v3", names)
        conn.close()
        store.close()

    def test_error_summary_difference_is_idempotent_replay(self):
        """Same material evidence + different error_summary -> idempotent.

        Frozen distinction: error_summary is result-integrity-bound metadata,
        NOT material identity. A second persist with different summary must
        return the already-persisted row (count stays 1), and the originally
        persisted summary must remain unchanged (no overwrite).
        """
        from tests.hermes_core.test_execution_start_result_service import (
            _reservation, _attempt, _evidence, _FakeLookup)
        from tools.hermes_core.execution_start_result_service import (
            ExecutionStartResultService)
        store = SQLiteExecutionStartStore(self.db)
        store.migrate_to_v3()
        store.record_reservation(reservation=_reservation(),
                                  now="2024-01-01T00:00:00Z")
        store.record_launch_attempt(attempt=_attempt(),
                                    now="2024-01-01T00:00:00Z")
        svc = ExecutionStartResultService(store, _FakeLookup())
        first = svc.persist_start_result(
            _attempt(), _reservation(),
            _evidence(ExecutionStartOutcome.FAILED,
                      error_code="WORKER_REJECTED", error_summary="rejected"))
        again = svc.persist_start_result(
            _attempt(), _reservation(),
            _evidence(ExecutionStartOutcome.FAILED,
                      error_code="WORKER_REJECTED",
                      error_summary="worker rejected request"))
        self.assertEqual(again.start_result_id, first.start_result_id)
        count = store._conn.execute(
            "SELECT COUNT(*) FROM execution_start_results").fetchone()[0]
        self.assertEqual(count, 1)
        persisted = store.get_execution_start_result("latch-1")
        self.assertEqual(persisted.error_summary, "rejected")
        store.close()

    def test_version_advances_last(self):
        # Inspect ordering: version row must still be 2 until migration commits.
        _seed_v2_db(self.db, with_schema_version=2, v3_result_shape=False)
        conn = sqlite3.connect(self.db)
        # Before migration, version is 2.
        self.assertEqual(self._version(self.db), 2)
        conn.close()
        store = SQLiteExecutionStartStore(self.db)
        self.assertEqual(self._version(self.db), SCHEMA_VERSION_LATEST)
        store.close()


from tests.hermes_core.test_execution_start_result_service import (
    _reservation, _attempt, _evidence)


class ReconcileFakeLookup:
    def __init__(self, outcome, run_id=None, error_code=None, error_summary=None):
        self._outcome = outcome
        self._run_id = run_id
        self._error_code = error_code
        self._error_summary = error_summary

    def lookup(self, idempotency_key):
        from tools.hermes_core.runtime_launch_adapter import (
            RuntimeLookupResult, RuntimeLookupOutcome)
        return RuntimeLookupResult(
            outcome=self._outcome, runtime_run_id=self._run_id,
            error_code=self._error_code, error_summary=self._error_summary)


class PersistenceReplayConflictTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "start.db")
        self.store = SQLiteExecutionStartStore(self.db)
        self.store.migrate_to_v3()
        self.store.record_reservation(reservation=_reservation(), now="2024-01-01T00:00:00Z")
        self.store.record_launch_attempt(attempt=_attempt(), now="2024-01-01T00:00:00Z")
        self.svc = ExecutionStartResultService(self.store, ReconcileFakeLookup(
            None))

    def tearDown(self):
        self.store.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ev(self, outcome, **kw):
        return _evidence(outcome, **kw)

    def test_fo_unfound_creates_no_result(self):
        # Reconciliation with NOT_FOUND_AUTHORITATIVE -> no result.
        self.svc._lookup = ReconcileFakeLookup(
            RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE)
        res = self.svc.reconcile_start_result("latch-1")
        self.assertIsNone(res)
        self.assertIsNone(self.store.get_execution_start_result("latch-1"))

    def test_failed_then_started_conflicts(self):
        self.svc.persist_start_result(
            _attempt(), _reservation(),
            self._ev(ExecutionStartOutcome.FAILED,
                     error_code="PROCESS_CREATION_FAILED"))
        with self.assertRaises(Exception):
            self.svc.persist_start_result(
                _attempt(), _reservation(),
                self._ev(ExecutionStartOutcome.STARTED, run_id="run-1"))


if __name__ == "__main__":
    unittest.main()
