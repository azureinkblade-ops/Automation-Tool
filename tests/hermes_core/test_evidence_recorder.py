from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    EventLedger,
    EvidenceLedgerRecorder,
    EvidencePackageBuilder,
    EvidencePackageError,
    load_schema_catalog,
)


TASK_ID = "33333333-3333-3333-3333-333333333333"


class HermesEvidenceRecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def make_recorder(self, temp_dir: str) -> EvidenceLedgerRecorder:
        base_dir = Path(temp_dir)
        builder = EvidencePackageBuilder(self.catalog, base_dir=base_dir)
        ledger = EventLedger(base_dir / "events.jsonl")
        return EvidenceLedgerRecorder(ledger, builder)

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

    def test_verified_evidence_writes_one_ledger_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self.make_recorder(temp_dir)
            evidence_path = self.freeze_fixture(temp_dir)

            recorded = recorder.record_frozen_evidence(
                evidence_path,
                actor="tester",
                occurred_at="2026-08-01T10:01:00Z",
            )

            entries = recorder.ledger.replay()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].event_type, "evidence.frozen")
            self.assertEqual(entries[0].task_id, TASK_ID)
            self.assertEqual(entries[0].payload["evidence_package_id"], recorded.evidence.evidence_package_id)
            self.assertEqual(entries[0].payload["actor"], "tester")
            self.assertTrue(recorder.ledger.verify())

    def test_invalid_evidence_writes_no_ledger_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self.make_recorder(temp_dir)
            evidence_path = self.freeze_fixture(temp_dir)
            raw = json.loads(evidence_path.read_text(encoding="utf-8"))
            raw["notes"] = "tampered"
            evidence_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

            with self.assertRaises(EvidencePackageError):
                recorder.record_frozen_evidence(evidence_path)

            self.assertEqual(recorder.ledger.replay(), [])

    def test_replay_finds_latest_frozen_evidence_by_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self.make_recorder(temp_dir)
            evidence_path = self.freeze_fixture(temp_dir)
            recorder.record_frozen_evidence(
                evidence_path,
                occurred_at="2026-08-01T10:01:00Z",
                metadata={"purpose": "review"},
            )

            latest = recorder.latest_evidence(TASK_ID)

            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest["task_id"], TASK_ID)
            self.assertEqual(latest["metadata"], {"purpose": "review"})
            self.assertEqual(recorder.replay_latest_evidence()[TASK_ID], latest)


if __name__ == "__main__":
    unittest.main()
