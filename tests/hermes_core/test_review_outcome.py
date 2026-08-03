from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import EvidencePackageBuilder, ReviewOutcomeValidator, load_schema_catalog


TASK_ID = "99999999-9999-9999-9999-999999999999"
OUTCOME_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class HermesReviewOutcomeTests(unittest.TestCase):
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
            evidence_package_id="evidence-outcome-fixture",
            created_at="2026-08-01T10:00:00Z",
        )
        return base_dir / "evidence.json"

    def valid_review(self, evidence_path: Path) -> dict:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        artifact_id = evidence["inventory"][0]["artifact_id"]
        return {
            "review_id": "77777777-7777-7777-7777-777777777777",
            "task_id": TASK_ID,
            "evidence_package_id": "evidence-outcome-fixture",
            "reviewer": {
                "agent_id": "reviewer-1",
                "model_id": "local-model",
                "role": "architect_reviewer",
            },
            "started_at": "2026-08-01T10:05:00Z",
            "completed_at": "2026-08-01T10:06:00Z",
            "findings": [
                {
                    "finding_id": "F-001",
                    "severity": "info",
                    "summary": "No issue found.",
                    "evidence_refs": [artifact_id],
                    "confidence": 0.9,
                }
            ],
            "recommendation": "accept",
            "authority": {
                "can_modify_state": False,
                "can_authorize_execution": False,
                "can_execute": False,
            },
        }

    def valid_outcome(self) -> dict:
        return {
            "review_outcome_id": OUTCOME_ID,
            "task_id": TASK_ID,
            "evidence_package_id": "evidence-outcome-fixture",
            "review_ids": ["77777777-7777-7777-7777-777777777777"],
            "recorded_at": "2026-08-01T10:07:00Z",
            "status": "accepted",
            "summary": "Review completed with a clean evidence chain.",
            "authority": {
                "can_modify_state": False,
                "can_authorize_execution": False,
                "can_execute": False,
            },
        }

    def validator(self, temp_dir: str) -> ReviewOutcomeValidator:
        return ReviewOutcomeValidator(self.catalog, base_dir=temp_dir)

    def test_valid_review_outcome_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.valid_review(evidence_path)
            outcome = self.valid_outcome()

            result = self.validator(temp_dir).validate(
                outcome,
                evidence_path=evidence_path,
                reviews=[review],
            )

            self.assertTrue(result.valid)
            self.assertEqual(result.issues, [])
            self.assertEqual(result.review_outcome_id, OUTCOME_ID)
            self.assertEqual(result.status, "accepted")

    def test_mismatched_evidence_package_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.valid_review(evidence_path)
            outcome = self.valid_outcome()
            outcome["evidence_package_id"] = "wrong-evidence-package"

            result = self.validator(temp_dir).validate(
                outcome,
                evidence_path=evidence_path,
                reviews=[review],
            )

            self.assertFalse(result.valid)
            self.assertIn(
                "Review outcome evidence_package_id does not match evidence package",
                result.issues,
            )

    def test_unknown_review_reference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.valid_review(evidence_path)
            outcome = self.valid_outcome()
            outcome["review_ids"] = ["99999999-9999-9999-9999-999999999999"]

            result = self.validator(temp_dir).validate(
                outcome,
                evidence_path=evidence_path,
                reviews=[review],
            )

            self.assertFalse(result.valid)
            self.assertIn("Outcome references unknown review_id: 99999999-9999-9999-9999-999999999999", result.issues)


if __name__ == "__main__":
    unittest.main()
