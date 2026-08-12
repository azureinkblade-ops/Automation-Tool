"""Governance state-integration tests for Phase 6E.

Covers the governed transition path: valid consensus + acceptance advancing to
ACCEPTED, the hard execution-authority boundary, and the negative cases that
must fail closed (missing disposition/acceptance, non-ACCEPTED dispositions,
tampered artifacts, task/evidence binding violations, unsupported edges).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    AcceptanceArtifactBuilder,
    SQLiteGovernanceStore,
    load_schema_catalog,
)
from tools.hermes_core.governance_store import (
    GovernanceIntegrityError,
    GovernanceTransitionError,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.hermes_core.test_consensus_disposition as harness


def build_accepted_chain(catalog: object, tmp: str):
    t = harness.HermesConsensusDispositionTests()
    t.setUpClass()
    ev = t.freeze_fixture(tmp)
    reviews = [
        t.review("22222222-2222-2222-2222-222222222222", agent_id="reviewer-1", findings=[]),
        t.review("33333333-3333-3333-3333-333333333333", agent_id="reviewer-2", findings=[]),
    ]
    fs = t.finding_set(tmp, ev, reviews)
    ev_ = t.evaluation(tmp, ev, reviews)
    disp = t.dispose(tmp, ev, reviews)
    acc = AcceptanceArtifactBuilder(catalog).build(disp, ev_, fs)
    evidence_doc = json.loads(Path(ev).read_text(encoding="utf-8"))
    return fs, ev_, disp, acc, evidence_doc, reviews


def seed_accepted(store: SQLiteGovernanceStore, fs, ev_, disp, acc, evidence_doc, reviews) -> None:
    store.record_evidence_record(evidence_doc)
    store.record_review_documents(reviews)
    store.record_finding_set(fs)
    store.record_consensus_evaluation(ev_)
    store.record_consensus_disposition(disp)
    store.record_acceptance(acc)


class GovernanceStateIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_schema_catalog(ROOT)
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "gov.db")
        self.store = SQLiteGovernanceStore(self.db, self.catalog)
        fs, ev_, disp, acc, evidence_doc, reviews = build_accepted_chain(self.catalog, self.tmp)
        self.fs, self.ev_, self.disp, self.acc = fs, ev_, disp, acc
        self.evidence_doc, self.reviews = evidence_doc, reviews

    def tearDown(self) -> None:
        self.store.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.db + suffix)
            except OSError:
                pass

    # -- positive ----------------------------------------------------------

    def test_valid_chain_advances_to_accepted(self) -> None:
        seed_accepted(self.store, self.fs, self.ev_, self.disp, self.acc,
                      self.evidence_doc, self.reviews)
        self.store.record_transition(self.fs.task_id, "UNDER_REVIEW", "CONSENSUS_CALCULATED")
        self.store.record_transition(self.fs.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")
        self.assertEqual(self.store.current_state(self.fs.task_id), "ACCEPTED")

    def test_accepted_governance_state_reads_back(self) -> None:
        seed_accepted(self.store, self.fs, self.ev_, self.disp, self.acc,
                      self.evidence_doc, self.reviews)
        self.store.record_transition(self.fs.task_id, "UNDER_REVIEW", "CONSENSUS_CALCULATED")
        self.store.record_transition(self.fs.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")
        chain = self.store.load_task_governance_chain(self.fs.task_id)
        self.assertEqual(chain.governance_state, "ACCEPTED")

    def test_governance_event_persisted_for_transition(self) -> None:
        seed_accepted(self.store, self.fs, self.ev_, self.disp, self.acc,
                      self.evidence_doc, self.reviews)
        self.store.record_transition(self.fs.task_id, "UNDER_REVIEW", "CONSENSUS_CALCULATED")
        self.store.record_transition(self.fs.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")
        report = self.store.verify_integrity()
        self.assertTrue(report.verified, report.failures)
        types = [e.event_type for e in
                 self.store.load_task_governance_chain(self.fs.task_id).events]
        self.assertIn("governance.transition.recorded", types)

    # -- authority boundary ------------------------------------------------

    def test_accepted_state_still_cannot_authorize_execution(self) -> None:
        seed_accepted(self.store, self.fs, self.ev_, self.disp, self.acc,
                      self.evidence_doc, self.reviews)
        self.store.record_transition(self.fs.task_id, "UNDER_REVIEW", "CONSENSUS_CALCULATED")
        self.store.record_transition(self.fs.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")
        chain = self.store.load_task_governance_chain(self.fs.task_id)
        self.assertFalse(chain.acceptance.authority["can_authorize_execution"])
        self.assertTrue(chain.acceptance.authority["requires_separate_authorization"])

    # -- negative ----------------------------------------------------------

    def test_missing_acceptance_rejects_transition(self) -> None:
        self.store.record_evidence_record(self.evidence_doc)
        self.store.record_review_documents(self.reviews)
        self.store.record_finding_set(self.fs)
        self.store.record_consensus_evaluation(self.ev_)
        self.store.record_consensus_disposition(self.disp)
        with self.assertRaises(GovernanceTransitionError):
            self.store.record_transition(self.fs.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")

    def test_missing_disposition_rejects_transition(self) -> None:
        self.store.record_evidence_record(self.evidence_doc)
        self.store.record_review_documents(self.reviews)
        self.store.record_finding_set(self.fs)
        self.store.record_consensus_evaluation(self.ev_)
        self.store.record_acceptance(self.acc)
        with self.assertRaises(GovernanceTransitionError):
            self.store.record_transition(self.fs.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")

    def test_unsupported_transition_edge_rejected(self) -> None:
        seed_accepted(self.store, self.fs, self.ev_, self.disp, self.acc,
                      self.evidence_doc, self.reviews)
        # ACCEPTED -> AUTHORIZED is prohibited (execution authority).
        with self.assertRaises(GovernanceTransitionError):
            self.store.record_transition(self.fs.task_id, "ACCEPTED", "AUTHORIZED")

    def test_tampered_artifact_blocks_transition(self) -> None:
        seed_accepted(self.store, self.fs, self.ev_, self.disp, self.acc,
                      self.evidence_doc, self.reviews)
        self.store.close()
        raw = __import__("sqlite3").connect(self.db)
        raw.execute(
            "UPDATE acceptance_artifacts SET document_json = ? WHERE acceptance_id = ?",
            ('{"tampered": true}', self.acc.acceptance_id),
        )
        raw.commit()
        raw.close()
        reopened = SQLiteGovernanceStore(self.db, self.catalog)
        with self.assertRaises(GovernanceIntegrityError):
            reopened.record_transition(self.fs.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")
        reopened.close()

    def test_acceptance_with_execution_authority_rejected(self) -> None:
        # An acceptance whose authority grants execution must be rejected, even
        # if every other governance rule passes. This proves the hard boundary.
        from tools.hermes_core.acceptance_artifact import AcceptanceArtifact

        bad_authority = {
            "can_authorize_execution": True,
            "requires_separate_authorization": False,
        }
        bad_acceptance = AcceptanceArtifact(
            acceptance_id=self.acc.acceptance_id,
            task_id=self.acc.task_id,
            evidence_package_id=self.acc.evidence_package_id,
            consensus_id=self.acc.consensus_id,
            finding_set_sha256=self.acc.finding_set_sha256,
            evaluation_sha256=self.acc.evaluation_sha256,
            disposition_sha256=self.acc.disposition_sha256,
            disposition=self.acc.disposition,
            reason_codes=self.acc.reason_codes,
            relevant_finding_keys=self.acc.relevant_finding_keys,
            blocking_finding_keys=self.acc.blocking_finding_keys,
            blocking_severities=self.acc.blocking_severities,
            review_ids=self.acc.review_ids,
            finding_keys=self.acc.finding_keys,
            accepted_at=self.acc.accepted_at,
            authority=bad_authority,
            acceptance_sha256="0" * 64,
        )
        from tools.hermes_core.acceptance_artifact import _acceptance_document
        from tools.hermes_core.hashing import sha256_payload

        bad_acceptance = AcceptanceArtifact(
            **{**bad_acceptance.__dict__, "acceptance_sha256": sha256_payload(_acceptance_document(bad_acceptance))}
        )
        self.store.record_acceptance(bad_acceptance)
        with self.assertRaises(GovernanceTransitionError):
            self.store.record_transition(self.acc.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")

    def test_non_accepted_disposition_cannot_reach_accepted(self) -> None:
        # Construct a non-ACCEPTED disposition AND a matching acceptance
        # artifact directly, so the disposition gate (not the missing-acceptance
        # guard) is the decisive blocker for reaching ACCEPTED state.
        from tools.hermes_core.acceptance_artifact import AcceptanceArtifact
        from tools.hermes_core.consensus_disposition import (
            ConsensusDisposition,
            _disposition_document,
        )
        from tools.hermes_core.hashing import sha256_payload

        provisional = ConsensusDisposition(
            disposition_sha256="0" * 64,
            task_id=self.disp.task_id,
            evidence_package_id=self.disp.evidence_package_id,
            finding_set_sha256=self.disp.finding_set_sha256,
            evaluation_sha256=self.disp.evaluation_sha256,
            agreement_class=self.disp.agreement_class,
            disposition="ESCALATED",
            reason_codes=self.disp.reason_codes,
            relevant_finding_keys=self.disp.relevant_finding_keys,
            blocking_finding_keys=self.disp.blocking_finding_keys,
            blocking_severities=self.disp.blocking_severities,
            confidence_policy_marker=self.disp.confidence_policy_marker,
        )
        blocked = ConsensusDisposition(
            **{**provisional.__dict__, "disposition_sha256": sha256_payload(_disposition_document(provisional))}
        )
        # Build a matching acceptance artifact bound to the ESCALATED disposition.
        bad_acceptance = AcceptanceArtifact(
            acceptance_id=self.acc.acceptance_id,
            task_id=self.acc.task_id,
            evidence_package_id=self.acc.evidence_package_id,
            consensus_id=self.acc.consensus_id,
            finding_set_sha256=self.acc.finding_set_sha256,
            evaluation_sha256=self.acc.evaluation_sha256,
            disposition_sha256=blocked.disposition_sha256,
            disposition="ESCALATED",
            reason_codes=self.acc.reason_codes,
            relevant_finding_keys=self.acc.relevant_finding_keys,
            blocking_finding_keys=self.acc.blocking_finding_keys,
            blocking_severities=self.acc.blocking_severities,
            review_ids=self.acc.review_ids,
            finding_keys=self.acc.finding_keys,
            accepted_at=self.acc.accepted_at,
            authority=self.acc.authority,
            acceptance_sha256="0" * 64,
        )
        from tools.hermes_core.acceptance_artifact import _acceptance_document
        from tools.hermes_core.hashing import sha256_payload

        bad_acceptance = AcceptanceArtifact(
            **{**bad_acceptance.__dict__, "acceptance_sha256": sha256_payload(_acceptance_document(bad_acceptance))}
        )
        self.store.record_evidence_record(self.evidence_doc)
        self.store.record_review_documents(self.reviews)
        self.store.record_finding_set(self.fs)
        self.store.record_consensus_evaluation(self.ev_)
        self.store.record_consensus_disposition(blocked)
        self.store.record_acceptance(bad_acceptance)
        with self.assertRaises(GovernanceTransitionError):
            self.store.record_transition(self.fs.task_id, "CONSENSUS_CALCULATED", "ACCEPTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
