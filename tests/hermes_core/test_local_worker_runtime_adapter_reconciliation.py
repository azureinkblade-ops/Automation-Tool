"""EA-4D.3E-B reconciliation tests: worker-owned idempotency registry.

Proves same-key replay = one logical identity, conflicting lineage fails
closed, all four lookup outcomes, that lookup creates no work, and that an
unreadable/corrupt/wrong-schema registry yields UNKNOWN (never authoritative
absence). No process is created.
"""

import os
import shutil
import tempfile
import unittest

from tools.hermes_core.local_worker_runtime_adapter import (
    LocalWorkerIdempotencyRegistry,
    RuntimeAdapterConflictError,
)
from tools.hermes_core.runtime_launch_adapter import RuntimeLookupOutcome


class RegistryFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "idem.sqlite")
        self.registry = LocalWorkerIdempotencyRegistry(self.db)
        self.registry.initialize()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class ReplayTests(RegistryFixture):
    def test_same_key_same_lineage_replays_one_logical_run(self):
        self.registry.record_acceptance(
            idempotency_key="k1", launch_attempt_id="a1", runtime_run_id="r1")
        # Idempotent re-acceptance of the same logical identity is allowed.
        self.registry.record_acceptance(
            idempotency_key="k1", launch_attempt_id="a1", runtime_run_id="r1")
        res = self.registry.lookup("k1")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.FOUND_STARTED)
        self.assertEqual(res.runtime_run_id, "r1")

    def test_conflicting_same_key_lineage_fails_closed(self):
        self.registry.record_acceptance(
            idempotency_key="k1", launch_attempt_id="a1", runtime_run_id="r1")
        with self.assertRaises(RuntimeAdapterConflictError):
            self.registry.record_acceptance(
                idempotency_key="k1", launch_attempt_id="a2", runtime_run_id="r2")


class LookupOutcomeTests(RegistryFixture):
    def test_found_started(self):
        self.registry.record_acceptance(
            idempotency_key="k1", launch_attempt_id="a1", runtime_run_id="r1")
        res = self.registry.lookup("k1")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.FOUND_STARTED)
        self.assertEqual(res.runtime_run_id, "r1")

    def test_found_failed(self):
        # Simulate an authoritative FAILED registration via direct state set.
        import sqlite3
        conn = sqlite3.connect(self.db, isolation_level=None)
        conn.execute(
            "INSERT INTO local_worker_idempotency "
            "(idempotency_key, launch_attempt_id, runtime_run_id, state, recorded_at) "
            "VALUES (?, ?, ?, 'FAILED', ?)", ("k1", "a1", "r1", 1.0))
        conn.close()
        res = self.registry.lookup("k1")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.FOUND_FAILED)

    def test_validated_absent_row_not_found_authoritative(self):
        res = self.registry.lookup("never-recorded")
        self.assertEqual(
            res.outcome, RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE)

    def test_lookup_creates_no_work(self):
        before = self.registry.lookup("k1")
        # Repeated lookups on an empty/absent key never mutate the registry.
        for _ in range(3):
            again = self.registry.lookup("k1")
            self.assertEqual(
                again.outcome, RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE)
        self.assertEqual(before.outcome, again.outcome)


class CorruptRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unreadable_path_yields_unknown(self):
        # Point at a directory (not a file) so open/validate fails -> UNKNOWN,
        # never NOT_FOUND_AUTHORITATIVE.
        reg = LocalWorkerIdempotencyRegistry(os.path.join(self.tmp, "missing"))
        res = reg.lookup("k1")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.UNKNOWN)

    def test_wrong_schema_yields_unknown(self):
        import sqlite3
        db = os.path.join(self.tmp, "bad.sqlite")
        # Create a SQLite file WITHOUT the expected table.
        conn = sqlite3.connect(db, isolation_level=None)
        conn.execute("CREATE TABLE unrelated (x TEXT)")
        conn.close()
        reg = LocalWorkerIdempotencyRegistry(db)
        res = reg.lookup("k1")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.UNKNOWN)

    def test_corrupt_file_yields_unknown(self):
        db = os.path.join(self.tmp, "corrupt.sqlite")
        with open(db, "wb") as fh:
            fh.write(b"this is not a sqlite database")
        reg = LocalWorkerIdempotencyRegistry(db)
        res = reg.lookup("k1")
        self.assertEqual(res.outcome, RuntimeLookupOutcome.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
