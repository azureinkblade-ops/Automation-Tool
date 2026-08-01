from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    EvidencePackageBuilder,
    ReviewAssignmentBuilder,
    ReviewSessionBuilder,
    ReviewSessionError,
    ReviewerRegistry,
    load_schema_catalog,
)


TASK_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class HermesReviewSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def freeze_fixture(self, temp_dir: str) -> Path:
        base_dir = Path(temp_dir)
        (base_dir / "artifact.txt").write_text("evidence", encoding="utf-8")
        EvidencePackageBuilder(self.catalog, base_dir=base_dir).freeze_to_file(
            base_dir / "evidence.json",
            task_id=TASK_ID,
            artifacts=["artifact.txt"],
            evidence_package_id="evidence-session-fixture",
            created_at="2026-08-01T10:00:00Z",
        )
        return base_dir / "evidence.json"

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

    def ready_plan(self, temp_dir: str, evidence_path: Path):
        registry = ReviewerRegistry.from_documents(
            self.catalog,
            [self.reviewer("reviewer-1"), self.reviewer("reviewer-2"), self.reviewer("reviewer-3")],
        )
        return ReviewAssignmentBuilder(self.catalog, base_dir=temp_dir).build(
            current_state="READY_FOR_REVIEW",
            evidence_path=evidence_path,
            parent_ref="evidence-frozen-entry",
            registry=registry,
        )

    def test_builds_verifiable_review_session_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            plan = self.ready_plan(temp_dir, evidence_path)

            envelope = ReviewSessionBuilder().build(
                plan=plan,
                evidence_path=evidence_path,
                created_at="2026-08-01T10:10:00Z",
            )

            self.assertEqual(envelope.document["task_id"], TASK_ID)
            self.assertTrue(envelope.document["read_only"])
            self.assertEqual(len(envelope.document["assignments"]), 3)
            self.assertTrue(ReviewSessionBuilder().verify(envelope))

    def test_freeze_to_file_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            plan = self.ready_plan(temp_dir, evidence_path)
            output_path = Path(temp_dir) / "review-session.json"

            envelope = ReviewSessionBuilder().freeze_to_file(
                output_path,
                plan=plan,
                evidence_path=evidence_path,
                created_at="2026-08-01T10:10:00Z",
            )

            self.assertEqual(envelope.path, output_path)
            self.assertTrue(ReviewSessionBuilder().verify(output_path))

    def test_unready_plan_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            Path(temp_dir, "artifact.txt").write_text("changed", encoding="utf-8")
            registry = ReviewerRegistry.from_documents(
                self.catalog,
                [self.reviewer("reviewer-1"), self.reviewer("reviewer-2"), self.reviewer("reviewer-3")],
            )
            plan = ReviewAssignmentBuilder(self.catalog, base_dir=temp_dir).build(
                current_state="READY_FOR_REVIEW",
                evidence_path=evidence_path,
                parent_ref="evidence-frozen-entry",
                registry=registry,
            )

            with self.assertRaisesRegex(ReviewSessionError, "plan is not ready"):
                ReviewSessionBuilder().build(plan=plan, evidence_path=evidence_path)

    def test_hash_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            plan = self.ready_plan(temp_dir, evidence_path)
            output_path = Path(temp_dir) / "review-session.json"
            ReviewSessionBuilder().freeze_to_file(
                output_path,
                plan=plan,
                evidence_path=evidence_path,
                created_at="2026-08-01T10:10:00Z",
            )
            document = json.loads(output_path.read_text(encoding="utf-8"))
            document["assignments"][0]["model_id"] = "changed-model"
            output_path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ReviewSessionError, "hash mismatch"):
                ReviewSessionBuilder().verify(output_path)

    def test_read_only_flag_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            plan = self.ready_plan(temp_dir, evidence_path)
            envelope = ReviewSessionBuilder().build(plan=plan, evidence_path=evidence_path)
            document = dict(envelope.document)
            document["read_only"] = False

            with self.assertRaisesRegex(ReviewSessionError, "must be read-only"):
                ReviewSessionBuilder().verify(
                    type(envelope)(document=document)
                )


if __name__ == "__main__":
    unittest.main()
