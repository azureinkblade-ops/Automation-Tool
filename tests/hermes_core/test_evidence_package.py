from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    EvidencePackageBuilder,
    EvidencePackageError,
    SchemaValidationError,
    load_schema_catalog,
)


TASK_ID = "22222222-2222-2222-2222-222222222222"


class HermesEvidencePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def make_builder(self, temp_dir: str) -> EvidencePackageBuilder:
        return EvidencePackageBuilder(self.catalog, base_dir=temp_dir)

    def test_builds_schema_valid_frozen_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "artifact.txt").write_text("evidence", encoding="utf-8")
            builder = self.make_builder(temp_dir)

            package = builder.build(
                task_id=TASK_ID,
                artifacts=["artifact.txt"],
                created_at="2026-08-01T10:00:00Z",
            )

            self.assertTrue(package.document["frozen"])
            self.assertEqual(package.document["task_id"], TASK_ID)
            self.assertEqual(len(package.document["inventory"]), 1)
            self.catalog.validate("hermes.evidence", package.document)

    def test_freeze_to_file_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "artifact.txt").write_text("evidence", encoding="utf-8")
            builder = self.make_builder(temp_dir)
            output = base_dir / "evidence.json"

            package = builder.freeze_to_file(
                output,
                task_id=TASK_ID,
                artifacts=["artifact.txt"],
                created_at="2026-08-01T10:00:00Z",
            )

            self.assertEqual(package.path, output)
            self.assertTrue(builder.verify(output))

    def test_missing_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            builder = self.make_builder(temp_dir)

            with self.assertRaises(EvidencePackageError):
                builder.build(
                    task_id=TASK_ID,
                    artifacts=["missing.txt"],
                    created_at="2026-08-01T10:00:00Z",
                )

    def test_changed_artifact_invalidates_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            artifact = base_dir / "artifact.txt"
            artifact.write_text("evidence", encoding="utf-8")
            builder = self.make_builder(temp_dir)
            output = base_dir / "evidence.json"
            builder.freeze_to_file(
                output,
                task_id=TASK_ID,
                artifacts=["artifact.txt"],
                created_at="2026-08-01T10:00:00Z",
            )

            artifact.write_text("changed", encoding="utf-8")

            with self.assertRaises(EvidencePackageError):
                builder.verify(output)

    def test_changed_package_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "artifact.txt").write_text("evidence", encoding="utf-8")
            builder = self.make_builder(temp_dir)
            output = base_dir / "evidence.json"
            builder.freeze_to_file(
                output,
                task_id=TASK_ID,
                artifacts=["artifact.txt"],
                created_at="2026-08-01T10:00:00Z",
            )
            raw = json.loads(output.read_text(encoding="utf-8"))
            raw["notes"] = "tampered"
            output.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

            with self.assertRaises(EvidencePackageError):
                builder.verify(output)

    def test_unfrozen_package_is_rejected_by_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "artifact.txt").write_text("evidence", encoding="utf-8")
            builder = self.make_builder(temp_dir)
            package = builder.build(
                task_id=TASK_ID,
                artifacts=["artifact.txt"],
                created_at="2026-08-01T10:00:00Z",
            )
            package.document["frozen"] = False

            with self.assertRaises(SchemaValidationError):
                self.catalog.validate("hermes.evidence", package.document)


if __name__ == "__main__":
    unittest.main()
