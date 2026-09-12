from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    close_governance_store,
    EvidencePackageBuilder,
    ReviewAssignmentBuilder,
    ReviewRunnerStub,
    ReviewSessionBuilder,
    ReviewSessionError,
    ReviewerRegistry,
    load_schema_catalog,
    reset_governance_store_cache,
    set_governance_db_path_override,
)


TASK_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class HermesReviewRunnerStubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        set_governance_db_path_override(Path(self.tmp.name) / "review-runner-governance.db")

    def tearDown(self) -> None:
        close_governance_store()
        set_governance_db_path_override(None)
        reset_governance_store_cache()
        self.tmp.cleanup()

    def reviewer(self, agent_id: str) -> dict:
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

    def make_session(self, temp_dir: str) -> Path:
        base_dir = Path(temp_dir)
        (base_dir / "artifact.txt").write_text("evidence", encoding="utf-8")
        evidence_path = base_dir / "evidence.json"
        EvidencePackageBuilder(self.catalog, base_dir=base_dir).freeze_to_file(
            evidence_path,
            task_id=TASK_ID,
            artifacts=["artifact.txt"],
            evidence_package_id="evidence-runner-fixture",
            created_at="2026-08-01T10:00:00Z",
        )
        registry = ReviewerRegistry.from_documents(
            self.catalog,
            [self.reviewer("reviewer-1"), self.reviewer("reviewer-2"), self.reviewer("reviewer-3")],
        )
        plan = ReviewAssignmentBuilder(self.catalog, base_dir=base_dir).build(
            current_state="READY_FOR_REVIEW",
            evidence_path=evidence_path,
            parent_ref="evidence-frozen-entry",
            registry=registry,
        )
        session_path = base_dir / "review-session.json"
        ReviewSessionBuilder().freeze_to_file(
            session_path,
            plan=plan,
            evidence_path=evidence_path,
            created_at="2026-08-01T10:10:00Z",
        )
        return session_path

    def test_prepare_returns_pending_without_model_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = self.make_session(temp_dir)

            result = ReviewRunnerStub().prepare(session_path)

            self.assertEqual(result.status, "pending_model_runner")
            self.assertEqual(result.task_id, TASK_ID)
            self.assertEqual(result.assignment_count, 3)
            self.assertEqual(result.reason, "Model execution is not authorized in this phase")

    def test_prepare_rejects_tampered_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = self.make_session(temp_dir)
            document = json.loads(session_path.read_text(encoding="utf-8"))
            document["task_id"] = "changed"
            session_path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ReviewSessionError, "hash mismatch"):
                ReviewRunnerStub().prepare(session_path)

    def test_prepare_accepts_loaded_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = self.make_session(temp_dir)
            envelope = ReviewSessionBuilder().load(session_path)

            result = ReviewRunnerStub().prepare(envelope)

            self.assertEqual(result.evidence_package_id, "evidence-runner-fixture")


if __name__ == "__main__":
    unittest.main()
