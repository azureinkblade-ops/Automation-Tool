from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    EvidencePackageBuilder,
    ReviewAssignmentBuilder,
    ReviewAssignmentError,
    ReviewerRegistry,
    load_schema_catalog,
)


TASK_ID = "99999999-9999-9999-9999-999999999999"


class HermesReviewAssignmentTests(unittest.TestCase):
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
            evidence_package_id="evidence-assignment-fixture",
            created_at="2026-08-01T10:00:00Z",
        )
        return base_dir / "evidence.json"

    def reviewer(self, agent_id: str, status: str = "active") -> dict:
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
            "status": status,
        }

    def registry(self, count: int) -> ReviewerRegistry:
        return ReviewerRegistry.from_documents(
            self.catalog,
            [self.reviewer(f"reviewer-{index}") for index in range(1, count + 1)],
        )

    def builder(self, temp_dir: str) -> ReviewAssignmentBuilder:
        return ReviewAssignmentBuilder(self.catalog, base_dir=temp_dir)

    def test_builds_assignments_for_clean_evidence_and_active_reviewers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)

            plan = self.builder(temp_dir).build(
                current_state="READY_FOR_REVIEW",
                evidence_path=evidence_path,
                parent_ref="evidence-frozen-entry",
                registry=self.registry(3),
            )

            self.assertTrue(plan.ready)
            self.assertEqual(plan.task_id, TASK_ID)
            self.assertEqual(len(plan.assignments), 3)
            self.assertEqual(
                [assignment.review_role for assignment in plan.assignments],
                ["architect_reviewer", "security_reviewer", "implementation_reviewer"],
            )

    def test_stale_evidence_blocks_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            Path(temp_dir, "artifact.txt").write_text("changed", encoding="utf-8")

            plan = self.builder(temp_dir).build(
                current_state="READY_FOR_REVIEW",
                evidence_path=evidence_path,
                parent_ref="evidence-frozen-entry",
                registry=self.registry(3),
            )

            self.assertFalse(plan.ready)
            self.assertEqual(plan.assignments, [])
            self.assertIn("Evidence artifact hash mismatch", plan.reasons[0])

    def test_too_few_active_reviewers_blocks_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)

            plan = self.builder(temp_dir).build(
                current_state="READY_FOR_REVIEW",
                evidence_path=evidence_path,
                parent_ref="evidence-frozen-entry",
                registry=self.registry(2),
            )

            self.assertFalse(plan.ready)
            self.assertEqual(plan.assignments, [])
            self.assertIn("Need at least 3 active reviewers", plan.reasons[0])

    def test_custom_roles_are_applied_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)

            plan = self.builder(temp_dir).build(
                current_state="READY_FOR_REVIEW",
                evidence_path=evidence_path,
                parent_ref="evidence-frozen-entry",
                registry=self.registry(2),
                minimum_reviewers=2,
                review_roles=("security_reviewer", "architect_reviewer"),
            )

            self.assertTrue(plan.ready)
            self.assertEqual(
                [assignment.review_role for assignment in plan.assignments],
                ["security_reviewer", "architect_reviewer"],
            )

    def test_unknown_review_role_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)

            with self.assertRaisesRegex(ReviewAssignmentError, "Unknown review role"):
                self.builder(temp_dir).build(
                    current_state="READY_FOR_REVIEW",
                    evidence_path=evidence_path,
                    parent_ref="evidence-frozen-entry",
                    registry=self.registry(1),
                    minimum_reviewers=1,
                    review_roles=("publisher",),
                )


if __name__ == "__main__":
    unittest.main()
