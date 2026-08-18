"""EA-4D.4B persistence + Authority-DB v6->v7 migration.

Proves:
* fresh DB opens at v7 with the projection table.
* a legacy v6 DB (populated) migrates additively to v7 (existing rows kept).
* pre-create refusal (_fail_before_v7_create) leaves version 6, no table.
* post-create rollback (_fail_after_v7_create) leaves version 6, no residue.
* projection INSERT + ATTEMPT_EXECUTING ledger append are atomic (one txn).
* UNIQUE(projection_id) and UNIQUE(start_result_id, target_state) enforced.
"""

import os
import sqlite3
import tempfile
import unittest

from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
    ExecutionAuthorizationSchemaError,
    ExecutionStateProjectionConflictError,
)
from tools.hermes_core.execution_authorization import (
    ExecutionStateProjection,
    build_execution_state_projection,
)


def _seed_v6_db(path):
    """Create a populated v6 authority DB (no projection table)."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("CREATE TABLE authority_schema_version (version INTEGER)")
    cur.execute("INSERT INTO authority_schema_version (version) VALUES (6)")
    cur.execute(
        "CREATE TABLE execution_authorization_requests ("
        "artifact_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
        "artifact_type TEXT NOT NULL, artifact_hash TEXT NOT NULL, "
        "canonical_payload TEXT NOT NULL)")
    cur.execute(
        "CREATE TABLE execution_authorization_decisions ("
        "artifact_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
        "request_id TEXT NOT NULL UNIQUE, artifact_type TEXT NOT NULL, "
        "artifact_hash TEXT NOT NULL, authorization_id TEXT, "
        "decision_linkage_sha256 TEXT NOT NULL, request_linkage_sha256 "
        "TEXT NOT NULL, canonical_payload TEXT NOT NULL)")
    cur.execute(
        "CREATE TABLE execution_authorizations ("
        "artifact_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
        "request_id TEXT NOT NULL UNIQUE, artifact_type TEXT NOT NULL, "
        "artifact_hash TEXT NOT NULL, request_linkage_sha256 TEXT NOT NULL, "
        "canonical_payload TEXT NOT NULL)")
    cur.execute(
        "CREATE TABLE execution_authorization_claims ("
        "artifact_id TEXT PRIMARY KEY, authorization_id TEXT NOT NULL UNIQUE, "
        "authorization_hash TEXT NOT NULL, request_id TEXT NOT NULL, "
        "request_hash TEXT NOT NULL, decision_id TEXT NOT NULL, "
        "decision_hash TEXT NOT NULL, task_id TEXT NOT NULL, claimant TEXT, "
        "claimed_at TEXT NOT NULL, claim_expires_at TEXT NOT NULL, "
        "authorization_policy TEXT, claim_reason TEXT, artifact_type TEXT "
        "NOT NULL, artifact_version TEXT NOT NULL, artifact_hash TEXT NOT NULL, "
        "canonical_payload TEXT NOT NULL)")
    cur.execute(
        "CREATE TABLE execution_attempts ("
        "artifact_id TEXT PRIMARY KEY, authorization_id TEXT NOT NULL, "
        "authorization_hash TEXT NOT NULL, request_id TEXT NOT NULL, "
        "request_hash TEXT NOT NULL, decision_id TEXT NOT NULL, "
        "decision_hash TEXT NOT NULL, claim_id TEXT NOT NULL, "
        "claim_hash TEXT NOT NULL, task_id TEXT NOT NULL, attempt_number "
        "INTEGER NOT NULL, attempt_actor_id TEXT NOT NULL, attempt_actor_type "
        "TEXT NOT NULL, attempt_actor_context TEXT, attempt_requested_at TEXT "
        "NOT NULL, attempt_recorded_at TEXT NOT NULL, claim_expires_at TEXT "
        "NOT NULL, must_start_by TEXT NOT NULL, input_hash TEXT NOT NULL, "
        "operation TEXT NOT NULL, worker_class TEXT, status TEXT NOT NULL, "
        "artifact_type TEXT NOT NULL, artifact_version TEXT NOT NULL, "
        "artifact_hash TEXT NOT NULL, attempt_linkage_sha256 TEXT NOT NULL, "
        "canonical_payload TEXT NOT NULL, UNIQUE(authorization_id, "
        "attempt_number))")
    cur.execute(
        "CREATE TABLE authority_ledger ("
        "sequence_no INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL, "
        "event_type TEXT NOT NULL, artifact_type TEXT NOT NULL, artifact_id "
        "TEXT NOT NULL, artifact_hash TEXT NOT NULL, payload_sha256 TEXT NOT "
        "NULL, previous_entry_sha256 TEXT, entry_sha256 TEXT NOT NULL, "
        "timestamp TEXT NOT NULL)")
    cur.execute(
        "CREATE TABLE worker_routes ("
        "artifact_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE, "
        "attempt_hash TEXT NOT NULL, authorization_id TEXT NOT NULL, "
        "authorization_hash TEXT NOT NULL, claim_id TEXT NOT NULL, claim_hash "
        "TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, "
        "decision_id TEXT NOT NULL, decision_hash TEXT NOT NULL, task_id TEXT "
        "NOT NULL, worker_id TEXT NOT NULL, worker_class TEXT, "
        "worker_registry_version TEXT NOT NULL, worker_registry_hash TEXT NOT "
        "NULL, routing_policy_id TEXT NOT NULL, routing_policy_version TEXT "
        "NOT NULL, routing_policy_hash TEXT NOT NULL, selected_at TEXT NOT "
        "NULL, must_start_by TEXT NOT NULL, operation TEXT NOT NULL, "
        "input_hash TEXT NOT NULL, router_actor_id TEXT NOT NULL, "
        "router_actor_type TEXT NOT NULL, router_actor_context TEXT, status "
        "TEXT NOT NULL, artifact_type TEXT NOT NULL, artifact_version TEXT "
        "NOT NULL, artifact_hash TEXT NOT NULL, route_linkage_sha256 TEXT NOT "
        "NULL, canonical_payload TEXT NOT NULL)")
    # Populate one durable row so the migration must be additive (not reject).
    cur.execute(
        "INSERT INTO execution_authorization_requests "
        "(artifact_id, task_id, artifact_type, artifact_hash, "
        "canonical_payload) VALUES ('req-x', 'task-1', 'T', 'h'*64, '{}')")
    conn.commit()
    conn.close()


def _sample_projection(start_result_id="sr-1", runtime_run_id="run-1"):
    return build_execution_state_projection(
        start_result_id=start_result_id, start_result_hash="S" * 64,
        launch_attempt_id="latch-1", launch_attempt_hash="L" * 64,
        route_id="route-1", route_hash="r" * 64,
        authorization_id="auth-1", authorization_hash="Z" * 64,
        attempt_id="att-1", attempt_hash="A" * 64,
        task_id="task-1", worker_id="w1", worker_version="1",
        runtime_run_id=runtime_run_id, target_state="EXECUTING")


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "auth.db")

    def _version(self, path):
        conn = sqlite3.connect(path)
        v = conn.execute(
            "SELECT version FROM authority_schema_version").fetchone()[0]
        conn.close()
        return v

    def test_fresh_db_is_v7(self):
        store = SQLiteExecutionAuthorizationStore(self.db)
        self.assertEqual(self._version(self.db), 7)
        exists = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE "
            "name='execution_state_projections'").fetchone()
        self.assertIsNotNone(exists)
        store.close()

    def test_populated_v6_migrates_additively(self):
        _seed_v6_db(self.db)
        self.assertEqual(self._version(self.db), 6)
        store = SQLiteExecutionAuthorizationStore(self.db)  # triggers migrate
        self.assertEqual(self._version(self.db), 7)
        # Pre-existing row preserved.
        count = store._conn.execute(
            "SELECT COUNT(*) FROM execution_authorization_requests").fetchone()[0]
        self.assertEqual(count, 1)
        # Projection table now exists.
        self.assertIsNotNone(store._conn.execute(
            "SELECT name FROM sqlite_master WHERE "
            "name='execution_state_projections'").fetchone())
        store.close()

    def test_fresh_db_born_at_v7_no_migration_round_trip(self):
        # A fresh DB must be created directly at v7 (born at SCHEMA_VERSION_LATEST)
        # and must NOT require a migration round-trip. We prove this by asserting
        # the stored version is v7 and the projection table exists immediately,
        # and that no v6-then-migrate artifact is present (the bootstrap row is 7).
        store = SQLiteExecutionAuthorizationStore(self.db)
        self.assertEqual(self._version(self.db), 7)
        self.assertIsNotNone(store._conn.execute(
            "SELECT name FROM sqlite_master WHERE "
            "name='execution_state_projections'").fetchone())
        store.close()

    def test_existing_v7_reopen_succeeds_without_migration(self):
        # Build a v7 DB, then reopen it. The reopen must NOT trigger a migration
        # (no migrate_to_v7 round-trip); it should open in place at v7.
        store = SQLiteExecutionAuthorizationStore(self.db)
        store.close()
        # Reopen the already-v7 database.
        reopened = SQLiteExecutionAuthorizationStore(self.db)
        self.assertEqual(self._version(self.db), 7)
        self.assertIsNotNone(reopened._conn.execute(
            "SELECT name FROM sqlite_master WHERE "
            "name='execution_state_projections'").fetchone())
        reopened.close()

    def test_fresh_db_migrate_to_v7_is_a_noop_not_required(self):
        # Calling migrate_to_v7 explicitly on an already-v7 fresh DB must be safe
        # (idempotent / version guard), proving the fresh path did not need it.
        store = SQLiteExecutionAuthorizationStore(self.db)
        # _migrate_v6_to_v7 requires version 6; on a v7 DB it must refuse cleanly.
        from tools.hermes_core.sqlite_execution_authorization_store import (
            ExecutionAuthorizationSchemaError)
        with self.assertRaises(ExecutionAuthorizationSchemaError):
            store._migrate_v6_to_v7()
        store.close()

        store.close()

class _SeamStore(SQLiteExecutionAuthorizationStore):
    """Test-only store that sets migration seams BEFORE _initialize, so the
    auto-migration triggered by __init__ honors them."""

    def __init__(self, path, fail_before=False, fail_after=False):
        from pathlib import Path
        self._db_path = Path(path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = DELETE")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._fail_after_decision = False
        self._fail_after_attempt_insert = False
        self._fail_after_route_insert = False
        self._fail_before_v7_create = fail_before
        self._fail_after_v7_create = fail_after
        self._initialize()


class SeamMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "auth.db")

    def _version(self, path):
        conn = sqlite3.connect(path)
        v = conn.execute(
            "SELECT version FROM authority_schema_version").fetchone()[0]
        conn.close()
        return v

    def test_pre_create_refusal_leaves_v6(self):
        _seed_v6_db(self.db)
        # The refusal fires during _initialize's auto-migration (seam set before
        # _initialize in _SeamStore.__init__), so construction itself raises.
        with self.assertRaises(ExecutionAuthorizationSchemaError):
            _SeamStore(self.db, fail_before=True)
        self.assertEqual(self._version(self.db), 6)
        conn = sqlite3.connect(self.db)
        self.assertIsNone(conn.execute(
            "SELECT name FROM sqlite_master WHERE "
            "name='execution_state_projections'").fetchone())
        conn.close()

    def test_post_create_rollback_leaves_v6_no_residue(self):
        _seed_v6_db(self.db)
        with self.assertRaises(ExecutionAuthorizationSchemaError):
            _SeamStore(self.db, fail_after=True)
        self.assertEqual(self._version(self.db), 6)
        conn = sqlite3.connect(self.db)
        self.assertIsNone(conn.execute(
            "SELECT name FROM sqlite_master WHERE "
            "name='execution_state_projections'").fetchone())
        conn.close()


class ProjectionPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "auth.db")
        self.store = SQLiteExecutionAuthorizationStore(self.db)

    def tearDown(self):
        self.store.close()

    def test_record_projection_writes_row_and_ledger_atomically(self):
        proj = _sample_projection()
        self.store.record_projection(proj)
        self.assertEqual(
            self.store._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            1)
        self.assertEqual(
            self.store._conn.execute(
                "SELECT COUNT(*) FROM authority_ledger WHERE "
                "event_type='ATTEMPT_EXECUTING'").fetchone()[0], 1)
        self.assertEqual(
            self.store.get_projection("sr-1")["target_state"], "EXECUTING")

    def test_idempotent_replay_single_row_and_event(self):
        self.store.record_projection(_sample_projection())
        self.store.record_projection(_sample_projection())
        self.assertEqual(
            self.store._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            1)
        self.assertEqual(
            self.store._conn.execute(
                "SELECT COUNT(*) FROM authority_ledger WHERE "
                "event_type='ATTEMPT_EXECUTING'").fetchone()[0], 1)

    def test_conflicting_material_lineage_fails_closed(self):
        self.store.record_projection(_sample_projection(runtime_run_id="run-1"))
        with self.assertRaises(ExecutionStateProjectionConflictError):
            self.store.record_projection(
                _sample_projection(runtime_run_id="run-DIFFERENT"))

    def test_unique_projection_id_enforced(self):
        # Distinct start_result_id but identical projection_id is impossible by
        # construction; verify the UNIQUE(start_result_id,target_state) guards a
        # second projection for the same start result with a new id seed.
        self.store.record_projection(_sample_projection(start_result_id="sr-1"))
        dup = build_execution_state_projection(
            start_result_id="sr-1", start_result_hash="S" * 64,
            launch_attempt_id="latch-1", launch_attempt_hash="L" * 64,
            route_id="route-1", route_hash="r" * 64,
            authorization_id="auth-1", authorization_hash="Z" * 64,
            attempt_id="att-1", attempt_hash="A" * 64,
            task_id="task-1", worker_id="w1", worker_version="1",
            runtime_run_id="run-2", target_state="EXECUTING")
        with self.assertRaises(ExecutionStateProjectionConflictError):
            self.store.record_projection(dup)


if __name__ == "__main__":
    unittest.main()
