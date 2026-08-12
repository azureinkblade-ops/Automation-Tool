from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.hermes_core import (
    ArtifactBundle,
    EventLedger,
    StateTransitionError,
    TransitionRecorder,
    load_schema_catalog,
)

from tests.hermes_core.test_state_machine import acceptance_doc, authorization_doc, consensus_doc


TASK_ID = "11111111-1111-1111-1111-111111111111"


class HermesTransitionRecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def make_recorder(self, temp_dir: str) -> TransitionRecorder:
        return TransitionRecorder(EventLedger(Path(temp_dir) / "events.jsonl"), self.catalog)

    def test_valid_transition_writes_one_ledger_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self.make_recorder(temp_dir)
            recorded = recorder.record_transition(
                "CONSENSUS_CALCULATED",
                "ACCEPTED",
                TASK_ID,
                ArtifactBundle(consensus=consensus_doc(), event_parent_ref="consensus-1"),
                occurred_at="2026-08-01T10:00:00Z",
            )

            entries = recorder.ledger.replay()

            self.assertTrue(recorded.result.accepted)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].event_type, "governance.transition.accepted")
            self.assertEqual(entries[0].payload["from_state"], "CONSENSUS_CALCULATED")
            self.assertEqual(entries[0].payload["to_state"], "ACCEPTED")
            self.assertTrue(recorder.ledger.verify())

    def test_invalid_transition_writes_no_ledger_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self.make_recorder(temp_dir)

            with self.assertRaises(StateTransitionError):
                recorder.record_transition(
                    "ACCEPTED",
                    "AUTHORIZED",
                    TASK_ID,
                    ArtifactBundle(
                        acceptance=acceptance_doc(),
                        authorization=authorization_doc(),
                        event_parent_ref="acceptance-hash",
                    ),
                )

            self.assertEqual(recorder.ledger.replay(), [])

    def test_authorization_hash_mismatch_writes_no_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self.make_recorder(temp_dir)

            with self.assertRaises(StateTransitionError):
                recorder.record_transition(
                    "AWAITING_EXECUTION_AUTHORIZATION",
                    "AUTHORIZED",
                    TASK_ID,
                    ArtifactBundle(
                        acceptance=acceptance_doc(),
                        authorization=authorization_doc(parent_hash="wrong-hash"),
                        event_parent_ref="authorization-hash",
                        now=datetime(2026, 8, 1, tzinfo=timezone.utc),
                    ),
                )

            self.assertEqual(recorder.ledger.replay(), [])

    def test_replay_reconstructs_latest_task_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self.make_recorder(temp_dir)
            recorder.record_transition(
                "CONSENSUS_CALCULATED",
                "ACCEPTED",
                TASK_ID,
                ArtifactBundle(consensus=consensus_doc(), event_parent_ref="consensus-1"),
                occurred_at="2026-08-01T10:00:00Z",
            )
            recorder.record_transition(
                "ACCEPTED",
                "AWAITING_EXECUTION_AUTHORIZATION",
                TASK_ID,
                ArtifactBundle(acceptance=acceptance_doc(), event_parent_ref="acceptance-hash"),
                occurred_at="2026-08-01T10:01:00Z",
            )

            self.assertEqual(
                recorder.latest_state(TASK_ID),
                "AWAITING_EXECUTION_AUTHORIZATION",
            )
            self.assertEqual(
                recorder.replay_latest_states(),
                {TASK_ID: "AWAITING_EXECUTION_AUTHORIZATION"},
            )


if __name__ == "__main__":
    unittest.main()
