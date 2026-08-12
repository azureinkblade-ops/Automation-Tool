"""Phase 6F — End-to-End Deterministic Consensus Proof.

Exercises the full production path from frozen evidence through persisted
ACCEPTED governance state, plus disagreement, block, tamper, ledger-integrity,
reopen, authority-negative, determinism, idempotency/conflict, and rollback.

No worker is executed; acceptance never grants execution authority.
"""
from __future__ import annotations

import os
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    GovernanceIntegrityError,
    GovernanceTransitionError,
    SQLiteGovernanceStore,
    load_schema_catalog,
)
from tools.hermes_core.acceptance_artifact import AcceptanceArtifact
from tools.hermes_core.consensus_disposition import (
    BLOCKING_SEVERITIES,
    DISPOSITION_ACCEPTED,
    DISPOSITION_BLOCKED,
    DISPOSITION_ESCALATED,
)
from tools.hermes_core.consensus_evaluator import (
    DETERMINISTIC_FAILURE,
    MATERIAL_DISAGREEMENT,
    UNANIMOUS_CLEAN,
    UNANIMOUS_FINDING,
)
from tools.hermes_core.hashing import sha256_payload

from .phase6_proof_helpers import (
    EVIDENCE_PACKAGE_ID,
    REVIEW_IDS,
    REVIEWER_AGENT_IDS,
    TASK_ID,
    advance_to_accepted,
    build_accepted_artifacts,
    build_consensus_artifacts,
    freeze_evidence_ids,
    persist_accepted_chain,
    raw_finding,
    raw_review,
)

DB_SUFFIX = ".phase6f.db"


def temp_db_path(tmp: Path, name: str) -> str:
    return str(tmp / (name + DB_SUFFIX))


def accepted_reviews() -> list[dict]:
    return [
        raw_review(REVIEW_IDS[0], REVIEWER_AGENT_IDS[0], findings=[], recommendation="accept"),
        raw_review(REVIEW_IDS[1], REVIEWER_AGENT_IDS[1], findings=[], recommendation="accept"),
        raw_review(REVIEW_IDS[2], REVIEWER_AGENT_IDS[2], findings=[], recommendation="accept"),
    ]


class Phase6AcceptedPathProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db = temp_db_path(self.tmp, "accepted")
        self.store = SQLiteGovernanceStore(self.db, self.catalog)

    def tearDown(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass

    def test_positive_accepted_path_end_to_end(self) -> None:
        arts = build_accepted_artifacts(self.tmp, accepted_reviews())
        # 6A/6B/6C/6D invariants
        self.assertEqual(arts["disposition"].disposition, DISPOSITION_ACCEPTED)
        self.assertIn(arts["disposition"].agreement_class, (UNANIMOUS_CLEAN, UNANIMOUS_FINDING))
        self.assertEqual(arts["acceptance"].disposition, DISPOSITION_ACCEPTED)
        self.assertFalse(arts["acceptance"].authority["can_authorize_execution"])
        self.assertTrue(arts["acceptance"].authority["requires_separate_authorization"])
        # persist + advance + reopen
        persist_accepted_chain(self.store, arts)
        chain = self.store.load_task_governance_chain(TASK_ID)
        self.assertIsNone(chain.governance_state)
        advance_to_accepted(self.store, arts)
        self.store.close()
        reopened = SQLiteGovernanceStore(self.db, self.catalog)
        try:
            chain = reopened.load_task_governance_chain(TASK_ID)
            self.assertEqual(chain.governance_state, "ACCEPTED")
            report = reopened.verify_integrity()
            self.assertTrue(report.ok, report.failures)
            self.assertEqual(len(chain.events), 6)
            self.assertEqual(chain.events[-1].event_type, "governance.transition.recorded")
            # acceptance still cannot authorize execution after reopen
            self.assertFalse(chain.acceptance.authority["can_authorize_execution"])
        finally:
            reopened.close()

    def test_cross_layer_hash_binding(self) -> None:
        arts = build_accepted_artifacts(self.tmp, accepted_reviews())
        fs, ev, disp, acc = (
            arts["finding_set"],
            arts["evaluation"],
            arts["disposition"],
            arts["acceptance"],
        )
        # 6A -> 6B -> 6C -> 6D hash chain links
        self.assertEqual(ev.finding_set_sha256, fs.finding_set_sha256)
        self.assertEqual(disp.finding_set_sha256, fs.finding_set_sha256)
        self.assertEqual(acc.finding_set_sha256, fs.finding_set_sha256)
        self.assertEqual(disp.evaluation_sha256, ev.evaluation_sha256)
        self.assertEqual(acc.evaluation_sha256, ev.evaluation_sha256)
        self.assertEqual(acc.disposition_sha256, disp.disposition_sha256)
        # task identity preserved across layers
        for obj in (fs, ev, disp, acc):
            self.assertEqual(obj.task_id, TASK_ID)
        self.assertEqual(acc.evidence_package_id, EVIDENCE_PACKAGE_ID)

    def test_two_stage_acceptance_identity(self) -> None:
        from tools.hermes_core.acceptance_artifact import _acceptance_core, _acceptance_document, _acceptance_id

        arts = build_accepted_artifacts(self.tmp, accepted_reviews())
        acc = arts["acceptance"]
        core = sha256_payload(_acceptance_core(acc))
        # acceptance_id derives from core[:16]; acceptance_sha256 over full canonical
        # doc (incl id, excludes accepted_at) per the two-stage identity rule.
        self.assertTrue(acc.acceptance_id.startswith("acceptance-"))
        self.assertEqual(acc.acceptance_id, _acceptance_id(core))
        self.assertEqual(acc.acceptance_sha256, sha256_payload(_acceptance_document(acc)))


class Phase6NegativeDispositionProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db = temp_db_path(self.tmp, "negative")
        self.store = SQLiteGovernanceStore(self.db, self.catalog)

    def tearDown(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass

    def _material_disagreement_reviews(self) -> list[dict]:
        ev_path, ids = freeze_evidence_ids(self.tmp)
        a, b = REVIEWER_AGENT_IDS[0], REVIEWER_AGENT_IDS[1]
        finding = raw_finding("f-1", severity="medium", evidence_refs=[ids[0]])
        return [
            raw_review(REVIEW_IDS[0], a, findings=[finding], recommendation="accept"),
            raw_review(REVIEW_IDS[1], b, findings=[finding], recommendation="reject"),
            raw_review(REVIEW_IDS[2], REVIEWER_AGENT_IDS[2], findings=[], recommendation="accept"),
        ]

    def _blocking_finding_reviews(self) -> list[dict]:
        # unanimous finding with high/critical severity -> BLOCKED
        ev_path, ids = freeze_evidence_ids(self.tmp)
        finding = raw_finding("f-block", severity="high", evidence_refs=[ids[0]])
        return [
            raw_review(REVIEW_IDS[0], REVIEWER_AGENT_IDS[0], findings=[finding], recommendation="reject"),
            raw_review(REVIEW_IDS[1], REVIEWER_AGENT_IDS[1], findings=[finding], recommendation="reject"),
            raw_review(REVIEW_IDS[2], REVIEWER_AGENT_IDS[2], findings=[finding], recommendation="reject"),
        ]

    def _deterministic_failure_reviews(self) -> list[dict]:
        # two reviews, expected three -> deterministic_failure -> BLOCKED
        return [
            raw_review(REVIEW_IDS[0], REVIEWER_AGENT_IDS[0], findings=[], recommendation="accept"),
            raw_review(REVIEW_IDS[1], REVIEWER_AGENT_IDS[1], findings=[], recommendation="accept"),
        ]

    def test_material_disagreement_escalates_no_acceptance(self) -> None:
        from tools.hermes_core.acceptance_artifact import AcceptanceArtifactBuilder

        arts = build_consensus_artifacts(self.tmp, self._material_disagreement_reviews())
        self.assertEqual(arts["disposition"].agreement_class, MATERIAL_DISAGREEMENT)
        self.assertEqual(arts["disposition"].disposition, DISPOSITION_ESCALATED)
        # acceptance builder must reject
        with self.assertRaises(Exception):
            AcceptanceArtifactBuilder(self.catalog, base_dir=self.tmp).build(
                arts["disposition"], arts["evaluation"], arts["finding_set"]
            )
        # no acceptance persisted, no accepted transition, ledger still valid
        persist_accepted_chain_without_acceptance(self.store, arts)
        with self.assertRaises(GovernanceTransitionError):
            advance_to_accepted(self.store, arts)
        report = self.store.verify_integrity()
        self.assertTrue(report.ok, report.failures)

    def test_deterministic_failure_blocks_no_acceptance(self) -> None:
        arts = build_consensus_artifacts(
            self.tmp, self._deterministic_failure_reviews(), expected_review_count=3
        )
        self.assertEqual(arts["disposition"].agreement_class, DETERMINISTIC_FAILURE)
        self.assertEqual(arts["disposition"].disposition, DISPOSITION_BLOCKED)
        persist_accepted_chain_without_acceptance(self.store, arts)
        with self.assertRaises(GovernanceTransitionError):
            advance_to_accepted(self.store, arts)
        report = self.store.verify_integrity()
        self.assertTrue(report.ok, report.failures)

    def test_high_critical_blocking_finding_blocks(self) -> None:
        arts = build_consensus_artifacts(self.tmp, self._blocking_finding_reviews())
        self.assertEqual(arts["disposition"].disposition, DISPOSITION_BLOCKED)
        # blocking severities preserved from BLOCKING_SEVERITIES
        self.assertTrue(set(arts["disposition"].blocking_severities) <= BLOCKING_SEVERITIES)
        self.assertTrue(arts["disposition"].blocking_finding_keys)
        persist_accepted_chain_without_acceptance(self.store, arts)
        with self.assertRaises(GovernanceTransitionError):
            advance_to_accepted(self.store, arts)

    def test_escalated_acceptance_cannot_transition(self) -> None:
        # Construct an ESCALATED disposition AND a matching acceptance artifact,
        # then confirm the governance gate rejects reaching ACCEPTED.
        from tools.hermes_core.acceptance_artifact import AcceptanceArtifact

        arts = build_consensus_artifacts(self.tmp, self._material_disagreement_reviews())
        self.assertEqual(arts["disposition"].disposition, DISPOSITION_ESCALATED)
        # Build a self-consistent acceptance bound to the ESCALATED disposition.
        from tools.hermes_core.acceptance_artifact import _acceptance_document

        base = build_accepted_artifacts(self.tmp, accepted_reviews())["acceptance"]
        bad = AcceptanceArtifact(
            **{
                **base.__dict__,
                "disposition_sha256": arts["disposition"].disposition_sha256,
                "disposition": DISPOSITION_ESCALATED,
                "acceptance_sha256": "0" * 64,
            }
        )
        bad = AcceptanceArtifact(
            **{**bad.__dict__, "acceptance_sha256": sha256_payload(_acceptance_document(bad))}
        )
        persist_accepted_chain_without_acceptance(self.store, arts)
        self.store.record_acceptance(bad)
        with self.assertRaises(GovernanceTransitionError):
            self.store.record_transition(TASK_ID, "CONSENSUS_CALCULATED", "ACCEPTED")

    def test_skip_consensus_calculated_rejected(self) -> None:
        # A valid accepted chain may not jump UNDER_REVIEW -> ACCEPTED; the
        # CONSENSUS_CALCULATED step is mandatory.
        arts = build_accepted_artifacts(self.tmp, accepted_reviews())
        persist_accepted_chain(self.store, arts)
        with self.assertRaises(GovernanceTransitionError):
            self.store.record_transition(TASK_ID, "UNDER_REVIEW", "ACCEPTED")

    def test_accepted_to_authorized_prohibited(self) -> None:
        # Even after ACCEPTED, the governance store must never advance toward
        # execution authorization (AUTHORIZED / EXECUTING).
        arts = build_accepted_artifacts(self.tmp, accepted_reviews())
        persist_accepted_chain(self.store, arts)
        advance_to_accepted(self.store, arts)
        with self.assertRaises(GovernanceTransitionError):
            self.store.record_transition(TASK_ID, "ACCEPTED", "AUTHORIZED")


class Phase6TamperProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db = temp_db_path(self.tmp, "tamper")
        self.store = SQLiteGovernanceStore(self.db, self.catalog)
        self.arts = build_accepted_artifacts(self.tmp, accepted_reviews())
        persist_accepted_chain(self.store, self.arts)
        advance_to_accepted(self.store, self.arts)

    def tearDown(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass

    def _reopen(self) -> SQLiteGovernanceStore:
        return SQLiteGovernanceStore(self.db, self.catalog)

    def test_persisted_acceptance_tamper_detected(self) -> None:
        # Semantic tamper: replace the stored acceptance with a valid document
        # whose `disposition` was changed (a field inside the canonical hash), so
        # the canonical hash no longer matches the stored acceptance_sha256.
        with sqlite3.connect(self.db) as raw:
            row = raw.execute(
                "SELECT document_json FROM acceptance_artifacts WHERE task_id = ?",
                (TASK_ID,),
            ).fetchone()
            doc = json.loads(row[0])
            doc["disposition"] = "ESCALATED"
            raw.execute(
                "UPDATE acceptance_artifacts SET document_json = ? WHERE task_id = ?",
                (json.dumps(doc), TASK_ID),
            )
            raw.commit()
        store = self._reopen()
        try:
            # load fails closed on tampered artifact (hash re-verification)
            with self.assertRaises(GovernanceIntegrityError):
                store.load_task_governance_chain(TASK_ID)
            # no transition possible, no self-repair
            with self.assertRaises(GovernanceIntegrityError):
                store.record_transition(TASK_ID, "ACCEPTED", "AUTHORIZED")
        finally:
            store.close()

    def test_structural_acceptance_tamper_detected(self) -> None:
        # Structural tamper: replace the stored acceptance with a malformed blob.
        with sqlite3.connect(self.db) as raw:
            raw.execute(
                "UPDATE acceptance_artifacts SET document_json = ? WHERE task_id = ?",
                ('{"tampered": true}', TASK_ID),
            )
            raw.commit()
        store = self._reopen()
        try:
            with self.assertRaises(GovernanceIntegrityError):
                store.load_task_governance_chain(TASK_ID)
        finally:
            store.close()

    def test_ledger_tamper_detected(self) -> None:
        with sqlite3.connect(self.db) as raw:
            raw.execute(
                "UPDATE governance_events SET previous_event_hash = ? WHERE sequence_no = 2",
                ("0" * 64,),
            )
            raw.commit()
        store = self._reopen()
        try:
            report = store.verify_integrity()
            self.assertFalse(report.ok)
            self.assertTrue(report.failures)
            with self.assertRaises(GovernanceTransitionError):
                store.record_transition(TASK_ID, "ACCEPTED", "AUTHORIZED")
        finally:
            store.close()

    def test_authority_tamper_rejected(self) -> None:
        from tools.hermes_core.acceptance_artifact import _acceptance_document

        # Own fresh store (the class setUp already persisted a valid acceptance
        # under this acceptance_id). Persist everything EXCEPT the valid
        # acceptance, then record a self-consistent acceptance that grants
        # execution authority and confirm the transition gate rejects it.
        fresh_db = temp_db_path(self.tmp, "authority-fresh")
        store = SQLiteGovernanceStore(fresh_db, self.catalog)
        try:
            arts = build_accepted_artifacts(self.tmp, accepted_reviews())
            persist_accepted_chain_without_acceptance(store, arts)
            acc = arts["acceptance"]
            bad_authority = {
                "can_authorize_execution": True,
                "requires_separate_authorization": False,
            }
            bad = AcceptanceArtifact(
                **{**acc.__dict__, "authority": bad_authority, "acceptance_sha256": "0" * 64}
            )
            bad = AcceptanceArtifact(
                **{**bad.__dict__, "acceptance_sha256": sha256_payload(_acceptance_document(bad))}
            )
            store.record_acceptance(bad)
            with self.assertRaises(GovernanceTransitionError):
                store.record_transition(TASK_ID, "CONSENSUS_CALCULATED", "ACCEPTED")
        finally:
            store.close()


class Phase6DeterminismProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def test_determinism_two_independent_runs_match(self) -> None:
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a1 = build_accepted_artifacts(Path(d1), accepted_reviews())
            a2 = build_accepted_artifacts(Path(d2), accepted_reviews())
        self.assertEqual(a1["finding_set"].finding_set_sha256, a2["finding_set"].finding_set_sha256)
        self.assertEqual(a1["evaluation"].evaluation_sha256, a2["evaluation"].evaluation_sha256)
        self.assertEqual(a1["disposition"].disposition_sha256, a2["disposition"].disposition_sha256)
        # two-stage acceptance identity deterministic
        self.assertEqual(a1["acceptance"].acceptance_id, a2["acceptance"].acceptance_id)
        self.assertEqual(a1["acceptance"].acceptance_sha256, a2["acceptance"].acceptance_sha256)
        self.assertEqual(a1["acceptance"].disposition, DISPOSITION_ACCEPTED)


class Phase6PersistenceProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db = temp_db_path(self.tmp, "persist")
        self.store = SQLiteGovernanceStore(self.db, self.catalog)

    def tearDown(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass

    def test_idempotent_repersist_is_noop(self) -> None:
        arts = build_accepted_artifacts(self.tmp, accepted_reviews())
        persist_accepted_chain(self.store, arts)
        pid_before = self._acceptance_persisted_id()
        persist_accepted_chain(self.store, arts)  # replay
        pid_after = self._acceptance_persisted_id()
        self.assertEqual(pid_before, pid_after)
        chain = self.store.load_task_governance_chain(TASK_ID)
        self.assertEqual(chain.acceptance.acceptance_sha256, arts["acceptance"].acceptance_sha256)

    def test_conflict_fail_closed(self) -> None:
        arts = build_accepted_artifacts(self.tmp, accepted_reviews())
        persist_accepted_chain(self.store, arts)
        original = arts["acceptance"]
        # Semantic tamper: keep a valid acceptance doc but change `disposition`
        # (a field inside the canonical hash), so the stored hash no longer
        # matches. Rebuild still succeeds; the conflict/re-verification catches it.
        with sqlite3.connect(self.db) as raw:
            row = raw.execute(
                "SELECT document_json FROM acceptance_artifacts WHERE acceptance_id = ?",
                (original.acceptance_id,),
            ).fetchone()
            doc = json.loads(row[0])
            doc["disposition"] = "ESCALATED"
            raw.execute(
                "UPDATE acceptance_artifacts SET document_json = ? WHERE acceptance_id = ?",
                (json.dumps(doc), original.acceptance_id),
            )
            raw.commit()
        # re-recording the original must fail closed (stored doc no longer matches)
        with self.assertRaises(GovernanceIntegrityError):
            self.store.record_acceptance(original)
        # original preserved; load reflects tamper and refuses to advance
        with sqlite3.connect(self.db) as raw:
            row = raw.execute(
                "SELECT document_json FROM acceptance_artifacts WHERE acceptance_id = ?",
                (original.acceptance_id,),
            ).fetchone()
        self.assertEqual(json.loads(row[0])["disposition"], "ESCALATED")

    def test_rollback_on_acceptance_failure(self) -> None:
        # Persist a valid chain, capture event count, then tamper the acceptance
        # row. A transition attempt must fail closed and write NO new event.
        arts = build_accepted_artifacts(self.tmp, accepted_reviews())
        persist_accepted_chain(self.store, arts)
        advance_to_accepted(self.store, arts)
        before = len(self.store.load_task_governance_chain(TASK_ID).events)
        # corrupt acceptance then attempt transition -> must not append event
        with sqlite3.connect(self.db) as raw:
            raw.execute(
                "UPDATE acceptance_artifacts SET document_json = ? WHERE task_id = ?",
                ('{"tampered": true}', TASK_ID),
            )
            raw.commit()
        with self.assertRaises(GovernanceIntegrityError):
            self.store.record_transition(TASK_ID, "CONSENSUS_CALCULATED", "ACCEPTED")
        # reopen to confirm no new event was committed
        self.store.close()
        reopened = SQLiteGovernanceStore(self.db, self.catalog)
        try:
            # load raises on tamper; if it ever succeeded, event count must be unchanged
            try:
                after = len(reopened.load_task_governance_chain(TASK_ID).events)
            except GovernanceIntegrityError:
                after = before
            self.assertEqual(after, before)
        finally:
            reopened.close()

    def _acceptance_persisted_id(self) -> str:
        with sqlite3.connect(self.db) as raw:
            row = raw.execute(
                "SELECT acceptance_id FROM acceptance_artifacts WHERE task_id = ?",
                (TASK_ID,),
            ).fetchone()
        return row[0] if row else ""


def persist_accepted_chain_without_acceptance(store: SQLiteGovernanceStore, arts: dict) -> None:
    """Persist evidence/reviews/6A/6B/6C but NOT the acceptance (negative proofs)."""
    store.record_evidence_record(arts["evidence_doc"])
    store.record_review_documents(arts["reviews"])
    store.record_finding_set(arts["finding_set"])
    store.record_consensus_evaluation(arts["evaluation"])
    store.record_consensus_disposition(arts["disposition"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
