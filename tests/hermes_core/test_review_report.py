from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import EvidencePackageBuilder, ReviewReportValidator, load_schema_catalog


TASK_ID = "66666666-6666-6666-6666-666666666666"


class HermesReviewReportValidatorTests(unittest.TestCase):
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
            evidence_package_id="evidence-review-fixture",
            created_at="2026-08-01T10:00:00Z",
        )
        return base_dir / "evidence.json"

    def valid_review(self, evidence_path: Path) -> dict:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        artifact_id = evidence["inventory"][0]["artifact_id"]
        return {
            "review_id": "77777777-7777-7777-7777-777777777777",
            "task_id": TASK_ID,
            "evidence_package_id": "evidence-review-fixture",
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

    def validator(self, temp_dir: str) -> ReviewReportValidator:
        return ReviewReportValidator(self.catalog, base_dir=temp_dir)

    def test_valid_review_report_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)

            result = self.validator(temp_dir).validate(
                self.valid_review(evidence_path),
                evidence_path=evidence_path,
            )

            self.assertTrue(result.valid)
            self.assertEqual(result.issues, [])
            self.assertEqual(result.task_id, TASK_ID)
            self.assertEqual(result.recommendation, "accept")

    def test_task_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.valid_review(evidence_path)
            review["task_id"] = "88888888-8888-8888-8888-888888888888"

            result = self.validator(temp_dir).validate(review, evidence_path=evidence_path)

            self.assertFalse(result.valid)
            self.assertIn("Review task_id does not match evidence package task_id", result.issues)

    def test_unknown_evidence_ref_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.valid_review(evidence_path)
            review["findings"][0]["evidence_refs"] = ["artifact-missing"]

            result = self.validator(temp_dir).validate(review, evidence_path=evidence_path)

            self.assertFalse(result.valid)
            self.assertIn(
                "Finding F-001 references unknown evidence artifact: artifact-missing",
                result.issues,
            )

    def test_authority_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.valid_review(evidence_path)
            review["authority"]["can_execute"] = True

            result = self.validator(temp_dir).validate(review, evidence_path=evidence_path)

            self.assertFalse(result.valid)
            self.assertIn("Review authority.can_execute must be false", result.issues)

    def test_duplicate_finding_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.valid_review(evidence_path)
            review["findings"].append(dict(review["findings"][0]))

            result = self.validator(temp_dir).validate(review, evidence_path=evidence_path)

            self.assertFalse(result.valid)
            self.assertIn("Duplicate finding_id: F-001", result.issues)

    def test_missing_recommendation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.valid_review(evidence_path)
            del review["recommendation"]

            result = self.validator(temp_dir).validate(review, evidence_path=evidence_path)

            self.assertFalse(result.valid)
            self.assertIn(
                "hermes.review.recommendation is required for review decisions",
                result.issues,
            )

    def test_completed_before_started_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.valid_review(evidence_path)
            review["started_at"] = "2026-08-01T10:06:00Z"
            review["completed_at"] = "2026-08-01T10:05:00Z"

            result = self.validator(temp_dir).validate(review, evidence_path=evidence_path)

            self.assertFalse(result.valid)
            self.assertIn("Review completed_at must not be earlier than started_at", result.issues)


if __name__ == "__main__":
    unittest.main()
