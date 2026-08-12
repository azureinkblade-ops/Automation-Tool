"""Runtime governance provider + query-surface tests (plan §22, §12).

These prove the production seam wires the store WITHOUT weakening any Phase 6
boundary: ACCEPTED is governance acceptance only; the provider grants no
execution authority and invokes no worker.
"""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    get_governance_chain,
    get_governance_state,
    get_governance_store,
    is_governance_accepted,
    reset_governance_store_cache,
    set_governance_db_path_override,
    verify_governance_integrity,
)
from tools.hermes_core.governance_store import GovernanceStore, GovernanceStoreError
from tools.hermes_core.sqlite_governance_store import SQLiteGovernanceStore

from tests.hermes_core.phase6_proof_helpers import (
    advance_to_accepted,
    build_accepted_artifacts,
    persist_accepted_chain,
)
from tests.hermes_core.test_phase6_end_to_end import accepted_reviews


class RuntimeProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db = Path(self.tmp) / "runtime.db"
        set_governance_db_path_override(self.db)

    def tearDown(self) -> None:
        set_governance_db_path_override(None)
        reset_governance_store_cache()

    def test_provider_bootstraps_fresh_store(self) -> None:
        store = get_governance_store()
        self.assertIsInstance(store, GovernanceStore)
        self.assertTrue(self.db.exists())

    def test_provider_reuses_same_instance(self) -> None:
        first = get_governance_store()
        second = get_governance_store()
        self.assertIs(first, second)

    def test_provider_creates_parent_directory_on_open(self) -> None:
        nested = Path(self.tmp) / "a" / "b" / "runtime.db"
        set_governance_db_path_override(nested)
        get_governance_store()
        self.assertTrue(nested.exists())

    def test_resolver_alone_creates_nothing(self) -> None:
        # Covered by config tests; guard here too: reset cache without override.
        from tools.hermes_core.runtime_config import resolve_governance_db_path

        target = Path(self.tmp) / "never_created.db"
        resolve_governance_db_path(
            {"HERMES_GOVERNANCE_DB": str(target)}
        )
        self.assertFalse(target.exists())


class RuntimeFirstConsumerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db = Path(self.tmp) / "runtime.db"
        set_governance_db_path_override(self.db)
        arts = build_accepted_artifacts(Path(self.tmp), accepted_reviews())
        persist_accepted_chain(get_governance_store(), arts)
        advance_to_accepted(get_governance_store(), arts)
        self.task_id = arts["finding_set"].task_id

    def tearDown(self) -> None:
        set_governance_db_path_override(None)
        reset_governance_store_cache()

    def test_loads_governance_chain(self) -> None:
        chain = get_governance_chain(self.task_id)
        self.assertEqual(chain.governance_state, "ACCEPTED")

    def test_reads_accepted_status(self) -> None:
        self.assertTrue(is_governance_accepted(self.task_id))
        self.assertEqual(get_governance_state(self.task_id), "ACCEPTED")

    def test_missing_task_returns_none(self) -> None:
        self.assertIsNone(get_governance_state("does-not-exist"))
        self.assertFalse(is_governance_accepted("does-not-exist"))

    def test_integrity_verifies(self) -> None:
        report = verify_governance_integrity()
        self.assertTrue(report.ok)

    def test_corrupted_integrity_detected(self) -> None:
        # Break the ledger hash chain; a clean verify must report failure.
        with sqlite3.connect(self.db) as raw:
            raw.execute(
                "UPDATE governance_events SET previous_event_hash = '0'*64"
            )
        report = verify_governance_integrity()
        self.assertFalse(report.ok)

    def test_corruption_propagates_as_integrity_error(self) -> None:
        # Tamper the persisted acceptance doc; load must fail closed.
        with sqlite3.connect(self.db) as raw:
            raw.execute(
                "UPDATE acceptance_artifacts SET document_json = '{\"tampered\": true}'"
            )
        with self.assertRaises(GovernanceStoreError):
            get_governance_chain(self.task_id)


class RuntimeExecutionBoundaryTests(unittest.TestCase):
    """Plan §12: ACCEPTED must never become execution authorization."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db = Path(self.tmp) / "runtime.db"
        set_governance_db_path_override(self.db)
        arts = build_accepted_artifacts(Path(self.tmp), accepted_reviews())
        persist_accepted_chain(get_governance_store(), arts)
        advance_to_accepted(get_governance_store(), arts)
        self.task_id = arts["finding_set"].task_id

    def tearDown(self) -> None:
        set_governance_db_path_override(None)
        reset_governance_store_cache()

    def test_accepted_state_does_not_grant_execution_authority(self) -> None:
        chain = get_governance_chain(self.task_id)
        # Governance chain ends at ACCEPTED; the broader lifecycle states that
        # follow (AUTHORIZED / EXECUTING) are absent and must not be implied.
        self.assertEqual(chain.governance_state, "ACCEPTED")
        self.assertNotEqual(chain.governance_state, "AUTHORIZED")
        self.assertNotEqual(chain.governance_state, "EXECUTING")
        # The query surface must report ACCEPTED, never imply AUTHORIZED.
        self.assertEqual(get_governance_state(self.task_id), "ACCEPTED")
        self.assertNotEqual(get_governance_state(self.task_id), "AUTHORIZED")

    def test_provider_exposes_no_worker_invocation(self) -> None:
        # The provider surface returns data only. There is no callable on the
        # store that would launch a worker; assert the returned store type has
        # no execution-routing method.
        store = get_governance_store()
        self.assertIsInstance(store, SQLiteGovernanceStore)
        for forbidden in ("authorize_execution", "launch_worker", "route_to_worker"):
            self.assertFalse(hasattr(store, forbidden))

    def test_reading_accepted_does_not_transition(self) -> None:
        # Merely reading governance questions leaves state unchanged.
        before = get_governance_state(self.task_id)
        is_governance_accepted(self.task_id)
        get_governance_chain(self.task_id)
        verify_governance_integrity()
        after = get_governance_state(self.task_id)
        self.assertEqual(before, after)
        self.assertEqual(after, "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
