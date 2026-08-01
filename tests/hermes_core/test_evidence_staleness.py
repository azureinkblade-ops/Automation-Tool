from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    EvidencePackageBuilder,
    EvidenceStalenessChecker,
    load_schema_catalog,
)


TASK_ID = "44444444-4444-4444-4444-444444444444"


class HermesEvidenceStalenessTests(unittest.TestCase):
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

    def make_checker(self, temp_dir: str) -> EvidenceStalenessChecker:
        return EvidenceStalenessChecker(self.catalog, base_dir=temp_dir)

    def test_clean_evidence_is_review_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            checker = self.make_checker(temp_dir)

            report = checker.check(evidence_path)

            self.assertFalse(report.stale)
            self.assertTrue(report.review_eligible)
            self.assertTrue(report.package_hash_matches)
            self.assertTrue(report.schema_valid)
            self.assertEqual([artifact.status for artifact in report.artifacts], ["ok"])
            self.assertEqual(report.issues, [])

    def test_changed_artifact_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            Path(temp_dir, "artifact.txt").write_text("changed", encoding="utf-8")
            checker = self.make_checker(temp_dir)

            report = checker.check(evidence_path)

            self.assertTrue(report.stale)
            self.assertFalse(report.review_eligible)
            self.assertEqual(report.artifacts[0].status, "changed")
            self.assertIn("Evidence artifact hash mismatch", report.issues[0])

    def test_missing_artifact_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            Path(temp_dir, "artifact.txt").unlink()
            checker = self.make_checker(temp_dir)

            report = checker.check(evidence_path)

            self.assertTrue(report.stale)
            self.assertFalse(report.review_eligible)
            self.assertEqual(report.artifacts[0].status, "missing")
            self.assertIn("Evidence artifact missing", report.issues[0])

    def test_tampered_package_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            raw = json.loads(evidence_path.read_text(encoding="utf-8"))
            raw["notes"] = "tampered"
            evidence_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
            checker = self.make_checker(temp_dir)

            report = checker.check(evidence_path)

            self.assertTrue(report.stale)
            self.assertFalse(report.review_eligible)
            self.assertFalse(report.package_hash_matches)
            self.assertIn("Evidence package hash mismatch", report.issues)


if __name__ == "__main__":
    unittest.main()
