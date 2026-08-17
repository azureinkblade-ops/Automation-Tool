"""EA-4D.3B schema-correction tests: Start DB v1 -> v2 migration.

Authorized surface: tools/hermes_core/sqlite_execution_start_store.py only.
The correction adds ``reservation_hash`` (NOT NULL) to ``execution_launch_attempts``
and advances the Start DB schema from version 1 to version 2, migrating any
surviving v1 database deterministically (fresh or empty legacy table = mechanical;
populated legacy rows = reconstruct reservation_hash from a verified durable
ExecutionStartReservation, else fail closed).
"""

import os
import shutil
import sqlite3
import tempfile
import unittest

from tools.hermes_core.hashing import canonical_json, sha256_text
from tools.hermes_core.execution_start import (
    build_execution_start_reservation,
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    ExecutionStartReservationStatus,
)
from tools.hermes_core.sqlite_execution_start_store import (
    SQLiteExecutionStartStore,
    ExecutionStartSchemaError,
    ExecutionStartMigrationError,
    SCHEMA_VERSION_START,
    SCHEMA_VERSION_LEGACY,
    V1_LAUNCH_ATTEMPT_COLUMNS,
)

# Frozen v1 execution_launch_attempts DDL (committed baseline 584d823): 27 cols,
# NO reservation_hash.
V1_LAUNCH_ATTEMPTS_DDL = """
CREATE TABLE IF NOT EXISTS execution_launch_attempts (
    launch_attempt_id TEXT PRIMARY KEY,
    artifact_hash TEXT NOT NULL,
    reservation_id TEXT NOT NULL UNIQUE,
    route_id TEXT NOT NULL,
    route_hash TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    attempt_hash TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    authorization_hash TEXT NOT NULL,
    task_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    worker_class TEXT,
    worker_version TEXT NOT NULL,
    operation TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    runtime_binding_id TEXT NOT NULL,
    runtime_binding_version TEXT NOT NULL,
    runtime_binding_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    must_start_by TEXT NOT NULL,
    launcher_actor_id TEXT NOT NULL,
    launcher_actor_type TEXT NOT NULL,
    launcher_actor_context TEXT,
    status TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
)
"""

V1_RESERVATIONS_DDL = """
CREATE TABLE IF NOT EXISTS execution_start_reservations (
    reservation_id TEXT PRIMARY KEY,
    artifact_hash TEXT NOT NULL,
    route_id TEXT NOT NULL UNIQUE,
    route_hash TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    attempt_hash TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    authorization_hash TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    claim_hash TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    decision_hash TEXT NOT NULL,
    task_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    worker_class TEXT,
    worker_version TEXT NOT NULL,
    operation TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    reserved_at TEXT NOT NULL,
    must_start_by TEXT NOT NULL,
    launcher_actor_id TEXT NOT NULL,
    launcher_actor_type TEXT NOT NULL,
    launcher_actor_context TEXT,
    status TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
)
"""


def _seed_v1_db(path, *, with_schema_version=1, launch_attempt_rows=(), reservation_rows=()):
    """Create a raw v1 Start DB on disk (no migration logic) for migration tests."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS start_schema_version (version INTEGER)")
    conn.execute(
        "INSERT INTO start_schema_version (version) VALUES (?)",
        (with_schema_version,),
    )
    conn.execute(V1_RESERVATIONS_DDL)
    conn.execute(V1_LAUNCH_ATTEMPTS_DDL)
    for res in reservation_rows:
        canonical = canonical_json(res.to_canonical_dict())
        conn.execute(
            "INSERT INTO execution_start_reservations "
            "(reservation_id, artifact_hash, route_id, route_hash, attempt_id, "
            "attempt_hash, authorization_id, authorization_hash, claim_id, "
            "claim_hash, request_id, request_hash, decision_id, decision_hash, "
            "task_id, worker_id, worker_class, worker_version, operation, "
            "input_hash, reserved_at, must_start_by, launcher_actor_id, "
            "launcher_actor_type, launcher_actor_context, status, canonical_json, "
            "payload_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?)",
            (
                res.reservation_id, res.artifact_hash, res.route_id, res.route_hash,
                res.attempt_id, res.attempt_hash, res.authorization_id,
                res.authorization_hash, res.claim_id, res.claim_hash,
                res.request_id, res.request_hash, res.decision_id, res.decision_hash,
                res.task_id, res.worker_id, res.worker_class, res.worker_version,
                res.operation, res.input_hash, res.reserved_at, res.must_start_by,
                res.launcher_actor_id, res.launcher_actor_type,
                res.launcher_actor_context, res.status.value, canonical,
                sha256_text(canonical),
            ),
        )
    for row in launch_attempt_rows:
        canonical = canonical_json(row["canonical_dict"])
        conn.execute(
            "INSERT INTO execution_launch_attempts "
            "(launch_attempt_id, artifact_hash, reservation_id, route_id, "
            "route_hash, attempt_id, attempt_hash, authorization_id, "
            "authorization_hash, task_id, worker_id, worker_class, worker_version, "
            "operation, input_hash, runtime_binding_id, runtime_binding_version, "
            "runtime_binding_hash, idempotency_key, recorded_at, must_start_by, "
            "launcher_actor_id, launcher_actor_type, launcher_actor_context, "
            "status, canonical_json, payload_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?)",
            (
                row["launch_attempt_id"], row["artifact_hash"], row["reservation_id"],
                row["route_id"], row["route_hash"], row["attempt_id"],
                row["attempt_hash"], row["authorization_id"], row["authorization_hash"],
                row["task_id"], row["worker_id"], row["worker_class"],
                row["worker_version"], row["operation"], row["input_hash"],
                row["runtime_binding_id"], row["runtime_binding_version"],
                row["runtime_binding_hash"], row["idempotency_key"], row["recorded_at"],
                row["must_start_by"], row["launcher_actor_id"], row["launcher_actor_type"],
                row["launcher_actor_context"], row["status"], canonical,
                sha256_text(canonical),
            ),
        )
    conn.commit()
    conn.close()


def _fresh_v1_dir():
    return tempfile.mkdtemp(prefix="ea4d3b-v1-")


class FreshV2CreationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ea4d3b-fresh-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_db_is_v2_with_reservation_hash(self):
        store = SQLiteExecutionStartStore(os.path.join(self.tmp, "start.db"))
        try:
            conn = store._conn
            version = conn.execute(
                "SELECT version FROM start_schema_version LIMIT 1"
            ).fetchone()["version"]
            self.assertEqual(version, SCHEMA_VERSION_START)
            cols = [
                r["name"] for r in conn.execute(
                    "PRAGMA table_info(execution_launch_attempts)").fetchall()
            ]
            self.assertIn("reservation_hash", cols)
        finally:
            store.close()


class V1ToV2MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = _fresh_v1_dir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _db_path(self):
        return os.path.join(self.tmp, "start.db")

    def test_empty_v1_migrates_to_v2(self):
        _seed_v1_db(self._db_path(), with_schema_version=SCHEMA_VERSION_LEGACY)
        store = SQLiteExecutionStartStore(self._db_path())  # triggers migration
        try:
            version = store._conn.execute(
                "SELECT version FROM start_schema_version LIMIT 1"
            ).fetchone()["version"]
            self.assertEqual(version, SCHEMA_VERSION_START)
            cols = [
                r["name"] for r in store._conn.execute(
                    "PRAGMA table_info(execution_launch_attempts)").fetchall()
            ]
            self.assertIn("reservation_hash", cols)
        finally:
            store.close()

    def test_migrated_v2_db_reopens(self):
        _seed_v1_db(self._db_path(), with_schema_version=SCHEMA_VERSION_LEGACY)
        SQLiteExecutionStartStore(self._db_path()).close()
        store = SQLiteExecutionStartStore(self._db_path())  # reopen v2
        try:
            version = store._conn.execute(
                "SELECT version FROM start_schema_version LIMIT 1"
            ).fetchone()["version"]
            self.assertEqual(version, SCHEMA_VERSION_START)
        finally:
            store.close()

    def test_populated_v1_reconstructs_reservation_hash(self):
        """A v1 DB with a launch-attempt row + matching verified reservation
        migrates by reconstructing reservation_hash from the reservation."""
        reservation = build_execution_start_reservation(
            reservation_id="res-1",
            route_id="route-1", route_hash="r" * 64,
            attempt_id="att-1", attempt_hash="a" * 64,
            authorization_id="auth-1", authorization_hash="z" * 64,
            claim_id="claim-1", claim_hash="c" * 64,
            request_id="req-1", request_hash="q" * 64,
            decision_id="dec-1", decision_hash="d" * 64,
            task_id="task-1", worker_id="worker-1", worker_class="run-sandbox",
            worker_version="1", operation="run-sandbox", input_hash="0" * 64,
            reserved_at="2024-01-01T00:00:00Z",
            must_start_by="2024-01-02T00:00:00Z",
            launcher_actor=ExecutionLauncherActor(
                actor_id="launcher-1", actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
                actor_context=None,
            ),
            status=ExecutionStartReservationStatus.RESERVED,
        )
        launch_row = {
            "launch_attempt_id": "latch-1",
            "artifact_hash": "L" * 64,
            "reservation_id": "res-1",
            "route_id": "route-1", "route_hash": "r" * 64,
            "attempt_id": "att-1", "attempt_hash": "a" * 64,
            "authorization_id": "auth-1", "authorization_hash": "z" * 64,
            "task_id": "task-1", "worker_id": "worker-1",
            "worker_class": "run-sandbox", "worker_version": "1",
            "operation": "run-sandbox", "input_hash": "0" * 64,
            "runtime_binding_id": "binding-1", "runtime_binding_version": "1",
            "runtime_binding_hash": "B" * 64,
            "idempotency_key": "i" * 64,
            "recorded_at": "2024-01-01T00:05:00Z",
            "must_start_by": "2024-01-02T00:00:00Z",
            "launcher_actor_id": "launcher-1",
            "launcher_actor_type": "SYSTEM_LAUNCHER",
            "launcher_actor_context": None,
            "status": "RECORDED",
            "canonical_dict": {
                "launch_attempt_id": "latch-1", "reservation_id": "res-1",
            },
        }
        _seed_v1_db(
            self._db_path(), with_schema_version=SCHEMA_VERSION_LEGACY,
            reservation_rows=[reservation], launch_attempt_rows=[launch_row],
        )
        store = SQLiteExecutionStartStore(self._db_path())
        try:
            got = store._conn.execute(
                "SELECT reservation_hash FROM execution_launch_attempts "
                "WHERE launch_attempt_id = 'latch-1'"
            ).fetchone()
            self.assertEqual(got["reservation_hash"], reservation.artifact_hash)
        finally:
            store.close()

    def test_populated_v1_missing_reservation_fails_closed(self):
        """A v1 launch-attempt row whose reservation is absent cannot be
        reconstructed -> migration must raise a typed error and leave v1."""
        launch_row = {
            "launch_attempt_id": "latch-orphan",
            "artifact_hash": "L" * 64,
            "reservation_id": "res-missing",
            "route_id": "route-1", "route_hash": "r" * 64,
            "attempt_id": "att-1", "attempt_hash": "a" * 64,
            "authorization_id": "auth-1", "authorization_hash": "z" * 64,
            "task_id": "task-1", "worker_id": "worker-1",
            "worker_class": "run-sandbox", "worker_version": "1",
            "operation": "run-sandbox", "input_hash": "0" * 64,
            "runtime_binding_id": "binding-1", "runtime_binding_version": "1",
            "runtime_binding_hash": "B" * 64,
            "idempotency_key": "i" * 64,
            "recorded_at": "2024-01-01T00:05:00Z",
            "must_start_by": "2024-01-02T00:00:00Z",
            "launcher_actor_id": "launcher-1",
            "launcher_actor_type": "SYSTEM_LAUNCHER",
            "launcher_actor_context": None,
            "status": "RECORDED",
            "canonical_dict": {"launch_attempt_id": "latch-orphan"},
        }
        _seed_v1_db(
            self._db_path(), with_schema_version=SCHEMA_VERSION_LEGACY,
            launch_attempt_rows=[launch_row],
        )
        with self.assertRaises(ExecutionStartMigrationError):
            SQLiteExecutionStartStore(self._db_path())
        # v1 database remains recognizable.
        conn = sqlite3.connect(self._db_path())
        version = conn.execute(
            "SELECT version FROM start_schema_version LIMIT 1"
        ).fetchone()[0]
        self.assertEqual(version, SCHEMA_VERSION_LEGACY)
        conn.close()

    def test_migration_fault_injection_leaves_v1(self):
        _seed_v1_db(self._db_path(), with_schema_version=SCHEMA_VERSION_LEGACY)
        # Arming the seam makes construction raise mid-migration; the v1 DB must
        # remain recognizable (rolled back, version still 1).
        store = SQLiteExecutionStartStore.__new__(SQLiteExecutionStartStore)
        store._db_path = None
        store._conn = sqlite3.connect(self._db_path(), isolation_level=None)
        store._conn.row_factory = sqlite3.Row
        store._conn.execute("PRAGMA foreign_keys = ON")
        store._fail_after_reservation_insert = False
        store._fail_during_migration = True
        with self.assertRaises(ExecutionStartMigrationError):
            store._initialize()
        store._conn.close()
        conn = sqlite3.connect(self._db_path())
        self.assertEqual(
            conn.execute("SELECT version FROM start_schema_version LIMIT 1").fetchone()[0],
            SCHEMA_VERSION_LEGACY,
        )
        conn.close()
        # Reopening without the seam migrates normally to v2.
        store2 = SQLiteExecutionStartStore(self._db_path())
        try:
            version = store2._conn.execute(
                "SELECT version FROM start_schema_version LIMIT 1"
            ).fetchone()["version"]
            self.assertEqual(version, SCHEMA_VERSION_START)
        finally:
            store2.close()

    def _open_migrating_store(self, *, fail_during=False, fail_after_schema=False):
        """Construct a store whose _initialize triggers the migration with a
        chosen seam armed, WITHOUT committing. Returns (store, raised)."""
        store = SQLiteExecutionStartStore.__new__(SQLiteExecutionStartStore)
        store._db_path = None
        store._conn = sqlite3.connect(self._db_path(), isolation_level=None)
        store._conn.row_factory = sqlite3.Row
        store._conn.execute("PRAGMA foreign_keys = ON")
        store._fail_after_reservation_insert = False
        store._fail_during_migration = fail_during
        store._fail_after_launch_attempt_schema_migration = fail_after_schema
        raised = None
        try:
            store._initialize()
        except ExecutionStartMigrationError as exc:
            raised = exc
        finally:
            store._conn.close()
        return store, raised

    def _assert_complete_v1_rollback(self, path, *, expect_rows=0):
        """Independently inspect the DB: must be fully v1 (no mutation residue)."""
        conn = sqlite3.connect(str(path))
        try:
            version = conn.execute(
                "SELECT version FROM start_schema_version LIMIT 1"
            ).fetchone()[0]
            self.assertEqual(version, SCHEMA_VERSION_LEGACY)
            cols = [
                r[1] for r in conn.execute(
                    "PRAGMA table_info(execution_launch_attempts)").fetchall()
            ]
            self.assertEqual(cols, list(V1_LAUNCH_ATTEMPT_COLUMNS))
            self.assertNotIn("reservation_hash", cols)
            # No temporary/rebuild table may survive.
            tables = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            self.assertNotIn("execution_launch_attempts_v2", tables)
            # Existing v1 data unchanged.
            n = conn.execute(
                "SELECT COUNT(*) FROM execution_launch_attempts"
            ).fetchone()[0]
            self.assertEqual(n, expect_rows)
        finally:
            conn.close()

    def test_post_mutation_rollback_empty_v1(self):
        """Injected failure AFTER the schema mutation (ALTER) but BEFORE the
        version row advances must roll back to a complete v1 database."""
        _seed_v1_db(self._db_path(), with_schema_version=SCHEMA_VERSION_LEGACY)
        _, raised = self._open_migrating_store(fail_after_schema=True)
        self.assertIsNotNone(raised, "seam should have raised")
        self._assert_complete_v1_rollback(self._db_path(), expect_rows=0)
        # Reopening without injection still migrates cleanly to v2.
        store = SQLiteExecutionStartStore(self._db_path())
        try:
            self.assertEqual(
                store._conn.execute(
                    "SELECT version FROM start_schema_version LIMIT 1"
                ).fetchone()["version"],
                SCHEMA_VERSION_START,
            )
        finally:
            store.close()

    def test_post_mutation_rollback_populated_v1(self):
        """Same post-mutation rollback proof for the populated-v1 rebuild path
        (which uses a different table-rebuild sequence)."""
        reservation = build_execution_start_reservation(
            reservation_id="res-1",
            route_id="route-1", route_hash="r" * 64,
            attempt_id="att-1", attempt_hash="a" * 64,
            authorization_id="auth-1", authorization_hash="z" * 64,
            claim_id="claim-1", claim_hash="c" * 64,
            request_id="req-1", request_hash="q" * 64,
            decision_id="dec-1", decision_hash="d" * 64,
            task_id="task-1", worker_id="worker-1", worker_class="run-sandbox",
            worker_version="1", operation="run-sandbox", input_hash="0" * 64,
            reserved_at="2024-01-01T00:00:00Z",
            must_start_by="2024-01-02T00:00:00Z",
            launcher_actor=ExecutionLauncherActor(
                actor_id="launcher-1",
                actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
                actor_context=None,
            ),
            status=ExecutionStartReservationStatus.RESERVED,
        )
        launch_row = {
            "launch_attempt_id": "latch-1",
            "artifact_hash": "L" * 64,
            "reservation_id": "res-1",
            "route_id": "route-1", "route_hash": "r" * 64,
            "attempt_id": "att-1", "attempt_hash": "a" * 64,
            "authorization_id": "auth-1", "authorization_hash": "z" * 64,
            "task_id": "task-1", "worker_id": "worker-1",
            "worker_class": "run-sandbox", "worker_version": "1",
            "operation": "run-sandbox", "input_hash": "0" * 64,
            "runtime_binding_id": "binding-1", "runtime_binding_version": "1",
            "runtime_binding_hash": "B" * 64,
            "idempotency_key": "i" * 64,
            "recorded_at": "2024-01-01T00:05:00Z",
            "must_start_by": "2024-01-02T00:00:00Z",
            "launcher_actor_id": "launcher-1",
            "launcher_actor_type": "SYSTEM_LAUNCHER",
            "launcher_actor_context": None,
            "status": "RECORDED",
            "canonical_dict": {"launch_attempt_id": "latch-1", "reservation_id": "res-1"},
        }
        _seed_v1_db(
            self._db_path(), with_schema_version=SCHEMA_VERSION_LEGACY,
            reservation_rows=[reservation], launch_attempt_rows=[launch_row],
        )
        _, raised = self._open_migrating_store(fail_after_schema=True)
        self.assertIsNotNone(raised, "seam should have raised")
        self._assert_complete_v1_rollback(self._db_path(), expect_rows=1)
        # Reopening without injection still reconstructs + migrates cleanly.
        store = SQLiteExecutionStartStore(self._db_path())
        try:
            self.assertEqual(
                store._conn.execute(
                    "SELECT version FROM start_schema_version LIMIT 1"
                ).fetchone()["version"],
                SCHEMA_VERSION_START,
            )
            got = store._conn.execute(
                "SELECT reservation_hash FROM execution_launch_attempts "
                "WHERE launch_attempt_id='latch-1'"
            ).fetchone()
            self.assertEqual(got["reservation_hash"], reservation.artifact_hash)
        finally:
            store.close()


class UnknownSchemaVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = _fresh_v1_dir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_future_schema_version_rejected(self):
        _seed_v1_db(os.path.join(self.tmp, "start.db"), with_schema_version=99)
        with self.assertRaises(ExecutionStartSchemaError):
            SQLiteExecutionStartStore(os.path.join(self.tmp, "start.db"))


class ReservationHashIntegrityTests(unittest.TestCase):
    """Round-trip + physical tamper detection on the v2 launch-attempt table."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ea4d3b-int-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reservation_hash_roundtrip(self):
        from tools.hermes_core.execution_launch_admission_service import (
            admit_execution_launch_attempt,
        )
        from tests.hermes_core.test_execution_launch_admission import (
            _build_canonical_chain, _persist_canonical_chain,
            _make_reservation, _persist_reservation, _make_binding_registry,
            _launcher_actor,
        )
        auth_tmp = tempfile.mkdtemp(prefix="ea4d3b-auth-")
        auth_store = None
        start_store = SQLiteExecutionStartStore(os.path.join(self.tmp, "start.db"))
        try:
            # Authority store must be a real authority DB; reuse the admission
            # test's fresh-authority helper indirectly via the service fixture.
            import tests.hermes_core.test_execution_launch_admission as m
            auth_tmp2, auth_store = m._fresh_authority_db()
            chain = _build_canonical_chain(seed="integrity")
            _persist_canonical_chain(auth_store, chain)
            reservation = _make_reservation(chain, launcher_actor=_launcher_actor())
            _persist_reservation(
                start_store, reservation,
                now=reservation.reserved_at, must_start_by=reservation.must_start_by,
            )
            attempt = admit_execution_launch_attempt(
                authority_store=auth_store,
                start_store=start_store,
                binding_registry=_make_binding_registry(chain),
                reservation_id=reservation.reservation_id,
                launcher_actor=_launcher_actor(),
            )
            got = start_store.get_launch_attempt(reservation.reservation_id)
            self.assertEqual(got.reservation_hash, reservation.artifact_hash)
            self.assertEqual(got.reservation_hash, attempt.reservation_hash)
            self.assertTrue(got.verify_hash())
        finally:
            start_store.close()
            if auth_store is not None:
                auth_store.close()
            shutil.rmtree(auth_tmp, ignore_errors=True)
            shutil.rmtree(auth_tmp2, ignore_errors=True)

    def test_physical_reservation_hash_tamper_detected(self):
        from tools.hermes_core.execution_launch_admission_service import (
            admit_execution_launch_attempt,
        )
        from tests.hermes_core.test_execution_launch_admission import (
            _build_canonical_chain, _persist_canonical_chain,
            _make_reservation, _persist_reservation, _make_binding_registry,
            _launcher_actor,
        )
        start_store = SQLiteExecutionStartStore(os.path.join(self.tmp, "start.db"))
        auth_tmp, auth_store = None, None
        try:
            import tests.hermes_core.test_execution_launch_admission as m
            auth_tmp, auth_store = m._fresh_authority_db()
            chain = _build_canonical_chain(seed="tamper")
            _persist_canonical_chain(auth_store, chain)
            reservation = _make_reservation(chain, launcher_actor=_launcher_actor())
            _persist_reservation(
                start_store, reservation,
                now=reservation.reserved_at, must_start_by=reservation.must_start_by,
            )
            admit_execution_launch_attempt(
                authority_store=auth_store,
                start_store=start_store,
                binding_registry=_make_binding_registry(chain),
                reservation_id=reservation.reservation_id,
                launcher_actor=_launcher_actor(),
            )
            # Physically corrupt the stored reservation_hash.
            start_store._conn.execute(
                "UPDATE execution_launch_attempts SET reservation_hash = ? "
                "WHERE reservation_id = ?",
                ("0" * 64, reservation.reservation_id),
            )
            start_store._conn.commit()
            from tools.hermes_core.execution_start import ExecutionStartIntegrityError
            with self.assertRaises(ExecutionStartIntegrityError):
                start_store.get_launch_attempt(reservation.reservation_id)
        finally:
            start_store.close()
            if auth_store is not None:
                auth_store.close()
            shutil.rmtree(auth_tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
