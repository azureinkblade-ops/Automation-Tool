"""Governance Consumer Integration Proof — real orchestration path.

Proves that ``ReviewRunnerStub.prepare()`` (the real, non-executing review
orchestration path) now observes authoritative Hermes governance truth through
the public consumer ``get_task_governance_status(task_id)``, and that the
integration remains observational: no execution authority, no worker, no
AUTHORIZED/EXECUTING transition, integrity fails closed.

The seam under test is real application code, not the isolated consumer tests.
"""

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    EvidencePackageBuilder,
    ReviewAssignmentBuilder,
    ReviewRunnerStub,
    ReviewSessionBuilder,
    ReviewerRegistry,
    get_governance_store,
    get_task_governance_status,
    load_schema_catalog,
    reset_governance_store_cache,
    set_governance_db_path_override,
)
from tools.hermes_core.governance_store import GovernanceIntegrityError

from tests.hermes_core.phase6_proof_helpers import (
    TASK_ID,
    advance_to_accepted,
    build_accepted_artifacts,
    persist_accepted_chain,
)
from tests.hermes_core.test_phase6_end_to_end import accepted_reviews


def _reviewer(agent_id: str) -> dict:
    return {
        "agent_id": agent_id,
        "display_name": agent_id,
        "role": "reviewer",
        "model_id": f"model-{agent_id}",
        "authority": {
            "can_review": True,
            "can_modify_governance_state": False,
            "can_authorize_execution": False,
            "can_execute": False,
        },
        "allowed_tools": [],
        "denied_tools": ["browser", "shell"],
        "status": "active",
    }


def _build_session(temp_dir: Path) -> Path:
    (temp_dir / "artifact.txt").write_text("evidence", encoding="utf-8")
    evidence_path = temp_dir / "evidence.json"
    EvidencePackageBuilder(load_schema_catalog(Path(__file__).resolve().parents[2]), base_dir=temp_dir).freeze_to_file(
        evidence_path,
        task_id=TASK_ID,
        artifacts=["artifact.txt"],
        evidence_package_id="evidence-integration-fixture",
        created_at="2026-08-01T10:00:00Z",
    )
    registry = ReviewerRegistry.from_documents(
        load_schema_catalog(Path(__file__).resolve().parents[2]),
        [_reviewer("reviewer-1"), _reviewer("reviewer-2"), _reviewer("reviewer-3")],
    )
    plan = ReviewAssignmentBuilder(
        load_schema_catalog(Path(__file__).resolve().parents[2]), base_dir=temp_dir
    ).build(
        current_state="READY_FOR_REVIEW",
        evidence_path=evidence_path,
        parent_ref="evidence-frozen-entry",
        registry=registry,
    )
    session_path = temp_dir / "review-session.json"
    ReviewSessionBuilder().freeze_to_file(
        session_path,
        plan=plan,
        evidence_path=evidence_path,
        created_at="2026-08-01T10:10:00Z",
    )
    return session_path


class ReviewRunnerGovernanceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db = Path(self.tmp) / "integration.db"
        set_governance_db_path_override(self.db)

    def tearDown(self) -> None:
        set_governance_db_path_override(None)
        reset_governance_store_cache()

    def _accept_task(self) -> None:
        arts = build_accepted_artifacts(Path(self.tmp), accepted_reviews())
        persist_accepted_chain(get_governance_store(), arts)
        advance_to_accepted(get_governance_store(), arts)

    # 1. Unknown task: envelope has a task_id with no governance record.
    def test_unknown_task_is_non_authorized(self) -> None:
        session_path = _build_session(Path(self.tmp))
        result = ReviewRunnerStub().prepare(session_path)
        self.assertEqual(result.task_id, TASK_ID)
        self.assertIsNotNone(result.governance)
        self.assertIsNone(result.governance.governance_state)
        self.assertFalse(result.governance.accepted)
        self.assertFalse(result.governance.can_authorize_execution)

    # 2. In-processing / non-accepted task (no ACCEPTED transition recorded).
    def test_in_processing_task_is_non_authorized(self) -> None:
        # Build the consensus chain up to evaluation but record no acceptance.
        from tests.hermes_core.phase6_proof_helpers import build_consensus_artifacts

        arts = build_consensus_artifacts(Path(self.tmp), accepted_reviews())
        store = get_governance_store()
        store.record_evidence_record(arts["evidence_doc"])
        store.record_review_documents(arts["reviews"])
        store.record_finding_set(arts["finding_set"])
        session_path = _build_session(Path(self.tmp))
        result = ReviewRunnerStub().prepare(session_path)
        self.assertIsNone(result.governance.governance_state)
        self.assertFalse(result.governance.accepted)
        self.assertFalse(result.governance.can_authorize_execution)

    # 3. Accepted task (mandatory): accepted=true, can_authorize_execution=false.
    def test_accepted_task_surfaces_accepted_but_not_authorized(self) -> None:
        self._accept_task()
        session_path = _build_session(Path(self.tmp))
        result = ReviewRunnerStub().prepare(session_path)
        self.assertEqual(result.governance.governance_state, "ACCEPTED")
        self.assertTrue(result.governance.accepted)
        # Mandatory invariant through the REAL orchestration path:
        self.assertFalse(result.governance.can_authorize_execution)

    # 4. Integrity corruption fails closed.
    def test_tampered_governance_fails_closed(self) -> None:
        import sqlite3

        self._accept_task()
        with sqlite3.connect(self.db) as raw:
            raw.execute(
                "UPDATE acceptance_artifacts SET document_json = '{\"tampered\": true}'"
            )
        session_path = _build_session(Path(self.tmp))
        with self.assertRaises(GovernanceIntegrityError):
            ReviewRunnerStub().prepare(session_path)

    # 5. No worker / execution side effects.
    def test_no_execution_side_effects(self) -> None:
        self._accept_task()
        store = get_governance_store()
        for forbidden in (
            "authorize_execution",
            "launch_worker",
            "enqueue_work",
            "create_execution_authorization",
            "execute_worker",
        ):
            self.assertFalse(hasattr(store, forbidden))
        session_path = _build_session(Path(self.tmp))
        before = store.load_task_governance_chain(TASK_ID).governance_state
        result = ReviewRunnerStub().prepare(session_path)
        after = store.load_task_governance_chain(TASK_ID).governance_state
        # Querying governance status via prepare() must not mutate it.
        self.assertEqual(before, after)
        self.assertEqual(after, "ACCEPTED")
        self.assertEqual(result.status, "pending_model_runner")

    # 6. Consumer invariant retained through the real path.
    def test_accepted_true_distinct_from_can_authorize_false(self) -> None:
        self._accept_task()
        session_path = _build_session(Path(self.tmp))
        result = ReviewRunnerStub().prepare(session_path)
        g = result.governance
        self.assertTrue(g.accepted)
        self.assertFalse(g.can_authorize_execution)
        self.assertNotEqual(g.accepted, g.can_authorize_execution)


if __name__ == "__main__":
    unittest.main()
