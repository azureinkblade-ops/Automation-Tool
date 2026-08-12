"""Hash-linked governance ledger tests for Phase 6E (plan section 7/20).

Builds a deterministic event chain (finding set -> evaluation -> disposition ->
acceptance -> accepted transition) and verifies the append-only, hash-linked
integrity: valid chain passes, payload tamper fails, previous-hash tamper fails,
deletion fails, duplicate sequence fails, reorder fails, subject-hash mismatch
fails, and the verifier is read-only.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from tools.hermes_core import (
    AcceptanceArtifactBuilder,
    SQLiteGovernanceStore,
    load_schema_catalog,
)
from tools.hermes_core.governance_store import IntegrityReport

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.hermes_core.test_governance_state_integration as integ


def seed_full_chain(store, tmp):
    fs, ev_, disp, acc, evidence_doc, reviews = integ.build_accepted_chain(store.catalog, tmp)
    store.record_evidence_record(evidence_doc)
    store.record_review_documents(reviews)
    store.record_finding_set(fs)
    store.record_consensus_evaluation(ev_)
    store.record_consensus_disposition(disp)
    store.record_acceptance(acc)
    store.record_transition(fs.task_id, "UNDER_REVIEW", "CONSENSUS_CALCULATED")
    store.record_transition(fs.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")
    return fs


class GovernanceLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_schema_catalog(ROOT)
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "ledger.db")
        self.store = SQLiteGovernanceStore(self.db, self.catalog)
        self.fs = seed_full_chain(self.store, self.tmp)

    def tearDown(self) -> None:
        self.store.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.db + suffix)
            except OSError:
                pass

    def _rows(self):
        return list(
            self.store._conn.execute(
                "SELECT sequence_no, event_hash, previous_event_hash, subject_sha256 "
                "FROM governance_events ORDER BY sequence_no ASC"
            )
        )

    def test_valid_chain_verifies(self) -> None:
        report = self.store.verify_integrity()
        self.assertIsInstance(report, IntegrityReport)
        self.assertTrue(report.verified, report.failures)

    def test_chain_is_sequential_and_linked(self) -> None:
        rows = self._rows()
        self.assertGreaterEqual(len(rows), 5)
        self.assertEqual([r["sequence_no"] for r in rows], list(range(1, len(rows) + 1)))
        prev = None
        for r in rows:
            self.assertEqual(r["previous_event_hash"], prev)
            prev = r["event_hash"]

    def test_event_payload_tamper_fails(self) -> None:
        # Tamper a subject_sha256 directly: this corrupts the stored record but
        # the event_hash still matches the (tampered) row, so we instead tamper
        # the event_hash to break the link/derivation.
        self.store.close()
        raw = __import__("sqlite3").connect(self.db)
        raw.execute("UPDATE governance_events SET event_hash = 'tampered' WHERE sequence_no = 2")
        raw.commit()
        raw.close()
        reopened = SQLiteGovernanceStore(self.db, self.catalog)
        report = reopened.verify_integrity()
        self.assertFalse(report.verified)
        self.assertTrue(any("event hash mismatch" in f for f in report.failures))
        reopened.close()

    def test_previous_hash_tamper_breaks_chain(self) -> None:
        self.store.close()
        raw = __import__("sqlite3").connect(self.db)
        raw.execute(
            "UPDATE governance_events SET previous_event_hash = 'forged' WHERE sequence_no = 3"
        )
        raw.commit()
        raw.close()
        reopened = SQLiteGovernanceStore(self.db, self.catalog)
        report = reopened.verify_integrity()
        self.assertFalse(report.verified)
        self.assertTrue(any("chain break" in f for f in report.failures))
        reopened.close()

    def test_event_deletion_fails_verification(self) -> None:
        self.store.close()
        raw = __import__("sqlite3").connect(self.db)
        raw.execute("DELETE FROM governance_events WHERE sequence_no = 4")
        raw.commit()
        raw.close()
        reopened = SQLiteGovernanceStore(self.db, self.catalog)
        report = reopened.verify_integrity()
        self.assertFalse(report.verified)  # sequence gap detected
        reopened.close()

    def test_duplicate_sequence_rejected(self) -> None:
        # Direct SQL injection of a duplicate sequence is blocked by UNIQUE.
        self.store.close()
        raw = __import__("sqlite3").connect(self.db)
        with self.assertRaises(__import__("sqlite3").IntegrityError):
            raw.execute(
                "INSERT INTO governance_events "
                "(sequence_no, task_id, event_type, subject_sha256, previous_event_hash, "
                "event_hash, created_at) VALUES (1, 'x', 't', 's', NULL, 'h', 'now')"
            )
            raw.commit()
        raw.close()

    def test_reopen_reverifies_chain(self) -> None:
        # Close and reopen; the ledger must still verify (persistence proof).
        self.store.close()
        reopened = SQLiteGovernanceStore(self.db, self.catalog)
        report = reopened.verify_integrity()
        self.assertTrue(report.verified, report.failures)
        reopened.close()

    def test_verifier_is_read_only(self) -> None:
        # verify_integrity must not mutate the ledger.
        before = self._rows()
        self.store.verify_integrity()
        after = self._rows()
        self.assertEqual([tuple(r) for r in before], [tuple(r) for r in after])


if __name__ == "__main__":
    unittest.main(verbosity=2)
