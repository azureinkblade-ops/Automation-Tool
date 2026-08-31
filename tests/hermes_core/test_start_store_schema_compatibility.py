"""R12E-R6F: Start-store creation and migration compatibility."""

import os
import sqlite3
import tempfile
import unittest

from tools.hermes_core.execution_start import (
    ExecutionStartOutcome,
    ExecutionStartResultConflictError,
)
from tools.hermes_core.execution_start_result_service import (
    ExecutionStartResultService,
)
from tools.hermes_core.execution_state_projection_orchestrator import (
    ExecutionStateProjectionOrchestrator,
)
from tools.hermes_core.execution_state_projector import ExecutionStateProjector
from tools.hermes_core.post_launch_execution_orchestrator import (
    PostLaunchExecutionOrchestrator,
    PostLaunchStatus,
)
from tools.hermes_core.runtime_launch_adapter import RuntimeLookupOutcome
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_execution_start_store import (
    SCHEMA_VERSION_LATEST,
    V3_RESULT_COLUMN_CONTRACT,
    ExecutionStartMigrationError,
    ExecutionStartSchemaError,
    SQLiteExecutionStartStore,
)
from tests.hermes_core.test_execution_start_result_persistence import (
    _seed_v2_db,
)
from tests.hermes_core.test_execution_start_result_service import (
    _FakeLookup,
    _attempt,
    _evidence,
    _reservation,
)
from tests.hermes_core.test_execution_start_store_migration import _seed_v1_db
from tests.hermes_core.test_post_launch_execution_orchestrator import (
    _Lookup as PostLaunchLookup,
    _attempt as post_launch_attempt,
    _reservation as post_launch_reservation,
)


class StartStoreSchemaCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ea4d4f-r6f-")
        self.db = os.path.join(self.tmp.name, "start.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _version(store):
        return store._conn.execute(
            "SELECT version FROM start_schema_version"
        ).fetchone()["version"]

    @staticmethod
    def _result_shape(store):
        return tuple(
            (row["name"], row["type"].upper(), row["notnull"], row["pk"])
            for row in store._conn.execute(
                "PRAGMA table_info(execution_start_results)"
            ).fetchall()
        )

    @staticmethod
    def _persist_started(store, run_id="run-r6f"):
        store.record_reservation(
            reservation=_reservation(), now="2024-01-01T00:00:00Z"
        )
        store.record_launch_attempt(
            attempt=_attempt(), now="2024-01-01T00:00:00Z"
        )
        return ExecutionStartResultService(store, _FakeLookup()).persist_start_result(
            _attempt(), _reservation(),
            _evidence(ExecutionStartOutcome.STARTED, run_id=run_id),
        )

    def test_fresh_database_is_complete_current_schema(self):
        store = SQLiteExecutionStartStore(self.db)
        try:
            self.assertEqual(self._version(store), SCHEMA_VERSION_LATEST)
            self.assertEqual(self._result_shape(store), V3_RESULT_COLUMN_CONTRACT)
            indexes = store._conn.execute(
                "PRAGMA index_list(execution_start_results)"
            ).fetchall()
            unique_columns = {
                tuple(
                    row["name"] for row in store._conn.execute(
                        f"PRAGMA index_info({index['name']})"
                    ).fetchall()
                )
                for index in indexes if index["unique"]
            }
            self.assertIn(("launch_attempt_id",), unique_columns)
        finally:
            store.close()

    def test_fresh_persistence_restart_and_replay(self):
        store = SQLiteExecutionStartStore(self.db)
        first = self._persist_started(store)
        self.assertEqual(first.runtime_binding_id, "binding-1")
        store.close()

        reopened = SQLiteExecutionStartStore(self.db)
        try:
            persisted = reopened.get_execution_start_result("latch-1")
            self.assertEqual(persisted.artifact_hash, first.artifact_hash)
            replay = ExecutionStartResultService(
                reopened, _FakeLookup()
            ).persist_start_result(
                _attempt(), _reservation(),
                _evidence(ExecutionStartOutcome.STARTED, run_id="run-r6f"),
            )
            self.assertEqual(replay.artifact_hash, first.artifact_hash)
            with self.assertRaises(ExecutionStartResultConflictError):
                ExecutionStartResultService(
                    reopened, _FakeLookup()
                ).persist_start_result(
                    _attempt(), _reservation(),
                    _evidence(ExecutionStartOutcome.STARTED, run_id="other-run"),
                )
        finally:
            reopened.close()

    def test_exact_empty_v2_shape_auto_migrates_and_persists(self):
        _seed_v2_db(self.db, with_schema_version=2, v3_result_shape=False)
        store = SQLiteExecutionStartStore(self.db)
        try:
            self.assertEqual(self._version(store), SCHEMA_VERSION_LATEST)
            self.assertEqual(self._result_shape(store), V3_RESULT_COLUMN_CONTRACT)
            result = self._persist_started(store, run_id="run-migrated-v2")
            self.assertEqual(result.runtime_binding_id, "binding-1")
        finally:
            store.close()

    def test_v1_auto_migrates_to_current_and_persists(self):
        _seed_v1_db(self.db, with_schema_version=1)
        store = SQLiteExecutionStartStore(self.db)
        try:
            self.assertEqual(self._version(store), SCHEMA_VERSION_LATEST)
            result = self._persist_started(store, run_id="run-migrated-v1")
            self.assertEqual(result.runtime_binding_id, "binding-1")
        finally:
            store.close()

    def test_populated_v2_refuses_without_mutation(self):
        row = (
            "srid-1", "a" * 64, "latch-old", "L" * 64, "res-old", "r" * 64,
            "route-old", "r" * 64, "task-old", "worker-old", "1", "STARTED",
            "2024-01-01T00:00:00Z", "run-old", None, None, "{}", "p" * 64,
        )
        _seed_v2_db(self.db, result_rows=[row])
        with self.assertRaises(ExecutionStartMigrationError):
            SQLiteExecutionStartStore(self.db)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT version FROM start_schema_version"
                ).fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM execution_start_results"
                ).fetchone()[0],
                1,
            )
        finally:
            connection.close()

    def test_current_version_with_old_result_shape_fails_closed(self):
        _seed_v2_db(
            self.db, with_schema_version=SCHEMA_VERSION_LATEST,
            v3_result_shape=False,
        )
        with self.assertRaisesRegex(
            ExecutionStartSchemaError, "incompatible.*physical shape"
        ):
            SQLiteExecutionStartStore(self.db)

    def test_current_version_with_wrong_column_contract_fails_closed(self):
        store = SQLiteExecutionStartStore(self.db)
        store.close()
        connection = sqlite3.connect(self.db)
        try:
            ddl = connection.execute(
                "SELECT sql FROM sqlite_master WHERE "
                "type='table' AND name='execution_start_results'"
            ).fetchone()[0]
            connection.execute(
                "ALTER TABLE execution_start_results RENAME TO old_results"
            )
            connection.execute(
                ddl.replace(
                    "runtime_binding_id TEXT NOT NULL",
                    "runtime_binding_id INTEGER NOT NULL",
                )
            )
            connection.execute("DROP TABLE old_results")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(
            ExecutionStartSchemaError, "incompatible.*physical shape"
        ):
            SQLiteExecutionStartStore(self.db)

    def test_post_open_shape_tamper_is_typed_before_insert(self):
        store = SQLiteExecutionStartStore(self.db)
        store.record_reservation(
            reservation=_reservation(), now="2024-01-01T00:00:00Z"
        )
        store.record_launch_attempt(
            attempt=_attempt(), now="2024-01-01T00:00:00Z"
        )
        fixture = os.path.join(self.tmp.name, "v2-fixture.sqlite3")
        _seed_v2_db(fixture)
        connection = sqlite3.connect(fixture)
        try:
            old_ddl = connection.execute(
                "SELECT sql FROM sqlite_master WHERE "
                "type='table' AND name='execution_start_results'"
            ).fetchone()[0]
        finally:
            connection.close()
        store._conn.execute("DROP TABLE execution_start_results")
        store._conn.execute(old_ddl)
        with self.assertRaises(ExecutionStartSchemaError) as raised:
            ExecutionStartResultService(store, _FakeLookup()).persist_start_result(
                _attempt(), _reservation(),
                _evidence(ExecutionStartOutcome.STARTED, run_id="run-r6f"),
            )
        self.assertNotIsInstance(raised.exception, sqlite3.OperationalError)
        store.close()

    def test_fresh_post_launch_reconciliation_crosses_r6_failure_boundary(self):
        auth_db = os.path.join(self.tmp.name, "authority.sqlite3")
        auth = SQLiteExecutionAuthorizationStore(auth_db)
        start = SQLiteExecutionStartStore(self.db)
        try:
            start.record_reservation(
                reservation=post_launch_reservation(),
                now="2024-01-01T00:00:00Z",
            )
            start.record_launch_attempt(
                attempt=post_launch_attempt(),
                now="2024-01-01T00:00:00Z",
            )
            result = PostLaunchExecutionOrchestrator(
                start_result_service=ExecutionStartResultService(
                    start, PostLaunchLookup(RuntimeLookupOutcome.FOUND_STARTED)
                ),
                projection_orchestrator=ExecutionStateProjectionOrchestrator(
                    projector=ExecutionStateProjector(start, auth), enabled=False,
                ),
            ).run_post_launch("latch-1")
            self.assertEqual(result.status, PostLaunchStatus.STARTED_NOT_PROJECTED)
            persisted = start.get_execution_start_result("latch-1")
            self.assertEqual(persisted.runtime_binding_id, "bind-1")
        finally:
            start.close()
            auth.close()

    def test_partial_existing_database_without_version_fails_closed(self):
        connection = sqlite3.connect(self.db)
        try:
            connection.execute("CREATE TABLE unrelated_state (value TEXT)")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(
            ExecutionStartSchemaError, "no schema-version table"
        ):
            SQLiteExecutionStartStore(self.db)


if __name__ == "__main__":
    unittest.main()
