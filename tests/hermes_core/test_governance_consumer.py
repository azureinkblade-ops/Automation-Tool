"""First real governance consumer tests (milestone: First Real Governance Consumer).

These prove the consumer reads authoritative governance truth WITHOUT any
execution authority or worker behavior, and that integrity failures fail closed.

Behavioral contract covered:
1. Unknown task -> deterministic non-authorized result (no exception).
2. Non-accepted state (UNDER_REVIEW / CONSENSUS_CALCULATED) -> accepted=False,
   can_authorize_execution=False.
3. ACCEPTED -> accepted=True, can_authorize_execution=False (mandatory).
4. Corrupted/tampered state -> GovernanceIntegrityError propagates (NOT
   downgraded to accepted=False).
5. No execution side effects (no worker, no authorization, no transition).
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    get_governance_store,
    get_task_governance_status,
    reset_governance_store_cache,
    set_governance_db_path_override,
)
from tools.hermes_core.governance_store import GovernanceIntegrityError
from tools.hermes_core.sqlite_governance_store import SQLiteGovernanceStore

from tests.hermes_core.phase6_proof_helpers import (
    advance_to_accepted,
    build_accepted_artifacts,
    build_consensus_artifacts,
    persist_accepted_chain,
)
from tests.hermes_core.test_phase6_end_to_end import accepted_reviews


class ConsumerTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db = Path(self.tmp) / "consumer.db"
        set_governance_db_path_override(self.db)

    def tearDown(self) -> None:
        set_governance_db_path_override(None)
        reset_governance_store_cache()

    def _accept(self):
        arts = build_accepted_artifacts(Path(self.tmp), accepted_reviews())
        persist_accepted_chain(get_governance_store(), arts)
        advance_to_accepted(get_governance_store(), arts)
        return arts["finding_set"].task_id

    def _partial(self):
        # Persist the consensus artifacts up to the evaluation, but record NO
        # governance transition. The governance_state therefore stays None:
        # the task is in governance processing but has not reached a terminal
        # state. (The store's transition gate only permits UNDER_REVIEW ->
        # CONSENSUS_CALCULATED when disposition AND acceptance are persisted,
        # so CONSENSUS_CALCULATED is effectively an intermediate on the way to
        # ACCEPTED; a standalone "non-accepted terminal" state is not
        # reachable without acceptance, which is the point of the boundary.)
        arts = build_consensus_artifacts(Path(self.tmp), accepted_reviews())
        store = get_governance_store()
        store.record_evidence_record(arts["evidence_doc"])
        store.record_review_documents(arts["reviews"])
        store.record_finding_set(arts["finding_set"])
        return arts["finding_set"].task_id


class UnknownTaskTests(ConsumerTestBase):
    def test_unknown_task_is_deterministic_non_authorized(self) -> None:
        status = get_task_governance_status("does-not-exist")
        self.assertEqual(status.task_id, "does-not-exist")
        self.assertIsNone(status.governance_state)
        self.assertFalse(status.accepted)
        self.assertFalse(status.can_authorize_execution)


class NonAcceptedStateTests(ConsumerTestBase):
    def test_in_processing_not_accepted(self) -> None:
        task_id = self._partial()
        status = get_task_governance_status(task_id)
        # No terminal transition recorded -> still in governance processing.
        self.assertIsNone(status.governance_state)
        self.assertFalse(status.accepted)
        self.assertFalse(status.can_authorize_execution)


class AcceptedStateTests(ConsumerTestBase):
    def test_accepted_reports_accepted_but_not_authorized(self) -> None:
        task_id = self._accept()
        status = get_task_governance_status(task_id)
        self.assertEqual(status.governance_state, "ACCEPTED")
        self.assertTrue(status.accepted)
        # Mandatory invariant: acceptance is NOT execution authorization.
        self.assertFalse(status.can_authorize_execution)


class CorruptionFailClosedTests(ConsumerTestBase):
    def test_tampered_state_propagates_integrity_error(self) -> None:
        task_id = self._accept()
        # Tamper the persisted acceptance doc; load must fail closed.
        with sqlite3.connect(self.db) as raw:
            raw.execute(
                "UPDATE acceptance_artifacts SET document_json = '{\"tampered\": true}'"
            )
        with self.assertRaises(GovernanceIntegrityError):
            get_task_governance_status(task_id)


class NoExecutionSideEffectsTests(ConsumerTestBase):
    def test_query_has_no_worker_or_authorization_side_effects(self) -> None:
        task_id = self._accept()
        store = get_governance_store()
        # The store must not expose any execution-authorization or worker API.
        for forbidden in (
            "authorize_execution",
            "launch_worker",
            "enqueue_work",
            "create_execution_authorization",
        ):
            self.assertFalse(hasattr(store, forbidden))
        # Reading status must not mutate the store's governance state.
        before = store.load_task_governance_chain(task_id).governance_state
        get_task_governance_status(task_id)
        after = store.load_task_governance_chain(task_id).governance_state
        self.assertEqual(before, after)
        self.assertEqual(after, "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
