from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import EvidencePackageBuilder, ReviewEligibilityGate, load_schema_catalog


TASK_ID = "55555555-5555-5555-5555-555555555555"


class HermesReviewGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def freeze_fixture(self, temp_dir: str) -> Path:
        base_dir = Path(temp_dir)
        (base_dir / "artifact.txt").write_text("evidence", encoding="utf-8")
        builder = EvidencePackageBuilder(self.catalog, base_dir=base_dir)
        builder.freeze_to_file(
            base_dir / "evidence.json",
            task_id=TASK_ID,
            artifacts=["artifact.txt"],
            created_at="2026-08-01T10:00:00Z",
        )
        return base_dir / "evidence.json"

    def make_gate(self, temp_dir: str) -> ReviewEligibilityGate:
        return ReviewEligibilityGate(self.catalog, base_dir=temp_dir)

    def test_ready_for_review_with_clean_evidence_is_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            gate = self.make_gate(temp_dir)

            decision = gate.check(
                current_state="READY_FOR_REVIEW",
                evidence_path=evidence_path,
                parent_ref="evidence-frozen-entry",
            )

            self.assertTrue(decision.eligible)
            self.assertEqual(decision.target_state, "UNDER_REVIEW")
            self.assertEqual(decision.task_id, TASK_ID)
            self.assertEqual(decision.reasons, ["review eligible"])

    def test_stale_evidence_blocks_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            Path(temp_dir, "artifact.txt").write_text("changed", encoding="utf-8")
            gate = self.make_gate(temp_dir)

            decision = gate.check(
                current_state="READY_FOR_REVIEW",
                evidence_path=evidence_path,
                parent_ref="evidence-frozen-entry",
            )

            self.assertFalse(decision.eligible)
            self.assertFalse(decision.staleness.review_eligible)
            self.assertIn("Evidence artifact hash mismatch", decision.reasons[0])

    def test_wrong_state_blocks_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            gate = self.make_gate(temp_dir)

            decision = gate.check(
                current_state="DRAFT",
                evidence_path=evidence_path,
                parent_ref="evidence-frozen-entry",
            )

            self.assertFalse(decision.eligible)
            self.assertIn("DRAFT -> UNDER_REVIEW", decision.reasons[0])

    def test_missing_parent_reference_blocks_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            gate = self.make_gate(temp_dir)

            decision = gate.check(
                current_state="READY_FOR_REVIEW",
                evidence_path=evidence_path,
                parent_ref=None,
            )

            self.assertFalse(decision.eligible)
            self.assertIn("parent event or artifact reference", decision.reasons[0])


if __name__ == "__main__":
    unittest.main()
