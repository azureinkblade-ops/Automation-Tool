from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    ArtifactRegistry,
    ArtifactRegistryError,
    EventLedger,
    LedgerError,
    sha256_payload,
)


class HermesLedgerTests(unittest.TestCase):
    def test_ledger_appends_and_replays_in_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = EventLedger(Path(temp_dir) / "events.jsonl")

            first = ledger.append(
                "task.requested",
                "task-1",
                {"title": "Build validator"},
                occurred_at="2026-08-01T10:00:00Z",
            )
            second = ledger.append(
                "task.validated",
                "task-1",
                {"result": "ok"},
                occurred_at="2026-08-01T10:01:00Z",
            )

            entries = ledger.replay()

            self.assertEqual([entry.sequence for entry in entries], [1, 2])
            self.assertEqual(first.previous_entry_sha256, None)
            self.assertEqual(second.previous_entry_sha256, first.entry_sha256)
            self.assertTrue(ledger.verify())

    def test_ledger_detects_payload_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            ledger = EventLedger(path)
            ledger.append(
                "task.requested",
                "task-1",
                {"title": "Original"},
                occurred_at="2026-08-01T10:00:00Z",
            )

            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["payload"]["title"] = "Tampered"
            path.write_text(json.dumps(raw, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaises(LedgerError):
                ledger.verify()

    def test_ledger_detects_chain_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            ledger = EventLedger(path)
            ledger.append("task.requested", "task-1", {"step": 1}, occurred_at="2026-08-01T10:00:00Z")
            ledger.append("task.validated", "task-1", {"step": 2}, occurred_at="2026-08-01T10:01:00Z")

            lines = path.read_text(encoding="utf-8").splitlines()
            second = json.loads(lines[1])
            second["previous_entry_sha256"] = "wrong"
            lines[1] = json.dumps(second, sort_keys=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            with self.assertRaises(LedgerError):
                ledger.verify()

    def test_payload_hash_is_deterministic(self) -> None:
        self.assertEqual(
            sha256_payload({"b": 2, "a": 1}),
            sha256_payload({"a": 1, "b": 2}),
        )


class HermesArtifactRegistryTests(unittest.TestCase):
    def test_artifact_registry_registers_and_verifies_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            artifact = base_dir / "artifact.txt"
            artifact.write_text("frozen evidence", encoding="utf-8")
            registry = ArtifactRegistry(base_dir / "registry.json", base_dir=base_dir)

            record = registry.register(
                "artifact.txt",
                artifact_id="artifact-1",
                schema_name="hermes.evidence",
                metadata={"kind": "evidence"},
                registered_at="2026-08-01T10:00:00Z",
            )

            self.assertEqual(record.artifact_id, "artifact-1")
            self.assertEqual(record.path, "artifact.txt")
            self.assertEqual(record.schema_name, "hermes.evidence")
            self.assertTrue(registry.verify("artifact-1"))

    def test_artifact_registry_detects_modified_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            artifact = base_dir / "artifact.txt"
            artifact.write_text("frozen evidence", encoding="utf-8")
            registry = ArtifactRegistry(base_dir / "registry.json", base_dir=base_dir)
            registry.register(
                "artifact.txt",
                artifact_id="artifact-1",
                schema_name="hermes.evidence",
                registered_at="2026-08-01T10:00:00Z",
            )

            artifact.write_text("changed evidence", encoding="utf-8")

            with self.assertRaises(ArtifactRegistryError):
                registry.verify("artifact-1")

    def test_artifact_registry_detects_record_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            artifact = base_dir / "artifact.txt"
            artifact.write_text("frozen evidence", encoding="utf-8")
            path = base_dir / "registry.json"
            registry = ArtifactRegistry(path, base_dir=base_dir)
            registry.register(
                "artifact.txt",
                artifact_id="artifact-1",
                schema_name="hermes.evidence",
                registered_at="2026-08-01T10:00:00Z",
            )

            raw = json.loads(path.read_text(encoding="utf-8"))
            raw[0]["schema_name"] = "hermes.task"
            path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

            with self.assertRaises(ArtifactRegistryError):
                registry.verify("artifact-1")

    def test_artifact_registry_rejects_missing_file_on_register(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ArtifactRegistry(Path(temp_dir) / "registry.json", base_dir=temp_dir)

            with self.assertRaises(ArtifactRegistryError):
                registry.register(
                    "missing.txt",
                    artifact_id="missing",
                    schema_name="hermes.evidence",
                )


if __name__ == "__main__":
    unittest.main()
