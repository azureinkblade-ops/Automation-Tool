from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.hermes_core import (
    AcceptanceArtifactBuilder,
    AcceptanceArtifactError,
    ConsensusDisposition,
    ConsensusEvaluation,
    NormalizedFindingSet,
    load_schema_catalog,
)
from tools.hermes_core.acceptance_artifact import _acceptance_document
from tools.hermes_core.consensus_disposition import (
    DISPOSITION_ACCEPTED,
    DISPOSITION_BLOCKED,
    DISPOSITION_ESCALATED,
    DISPOSITION_INCONCLUSIVE,
    DISPOSITION_REJECTED,
    _disposition_document,
    _finding_set_document,
)
from tools.hermes_core.consensus_evaluator import _evaluation_document
from tools.hermes_core.hashing import sha256_payload

import tests.hermes_core.test_consensus_disposition as mod

REVIEW_ONE = "22222222-2222-2222-2222-222222222222"
REVIEW_TWO = "33333333-3333-3333-3333-333333333333"


def _self_consistent_disposition(
    disposition, *, task_id, evidence_package_id, finding_set_sha256, evaluation_sha256
):
    """Build a ConsensusDisposition whose own hash verifies for the given value.

    Used so eligibility tests isolate the disposition-eligibility rule: the
    artifact's hash re-verification passes, leaving only the ACCEPTED gate as
    the thing standing between build and rejection.
    """
    base = ConsensusDisposition(
        task_id=task_id,
        evidence_package_id=evidence_package_id,
        finding_set_sha256=finding_set_sha256,
        evaluation_sha256=evaluation_sha256,
        agreement_class="unanimous_clean",
        disposition=disposition,
        reason_codes=("unanimous_clean", "unanimous_recommendation", "confidence_threshold_not_defined"),
        relevant_finding_keys=(),
        blocking_finding_keys=(),
        blocking_severities=(),
        confidence_policy_marker={"enforced": False, "reason": "numeric_threshold_not_defined"},
        disposition_sha256="",
    )
    return ConsensusDisposition(
        **{**base.__dict__, "disposition_sha256": sha256_payload(_disposition_document(base))}
    )


def _self_consistent_evaluation(evaluation_sha256, *, task_id, evidence_package_id, finding_set_sha256, review_ids):
    base = ConsensusEvaluation(
        task_id=task_id,
        evidence_package_id=evidence_package_id,
        finding_set_sha256=finding_set_sha256,
        agreement_class="unanimous_clean",
        review_ids=tuple(sorted(review_ids)),
        reviewer_agent_ids=("reviewer-1", "reviewer-2"),
        expected_review_count=2,
        finding_agreements=(),
        recommendations=("accept",),
        recommendation_conflict=False,
        reason_codes=("unanimous_clean",),
        evaluation_sha256="",
    )
    return ConsensusEvaluation(
        **{**base.__dict__, "evaluation_sha256": evaluation_sha256 or sha256_payload(_evaluation_document(base))}
    )


def _self_consistent_finding_set(finding_set_sha256, *, task_id, evidence_package_id, review_ids):
    base = NormalizedFindingSet(
        task_id=task_id,
        evidence_package_id=evidence_package_id,
        review_ids=tuple(sorted(review_ids)),
        findings=(),
        finding_set_sha256="",
    )
    return NormalizedFindingSet(
        **{**base.__dict__, "finding_set_sha256": finding_set_sha256 or sha256_payload(_finding_set_document(base))}
    )


class HermesAcceptanceArtifactTests(unittest.TestCase):
    """Phase 6D: deterministic acceptance artifact from a verified 6C disposition."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def setUp(self) -> None:
        # Reuse the 6C test harness fixtures/helpers.
        self.helper = mod.HermesConsensusDispositionTests()
        self.helper.setUpClass()

    def _accepted_chain(self, temp_dir, evidence_path, reviews):
        fs = self.helper.finding_set(temp_dir, evidence_path, reviews)
        ev = self.helper.evaluation(temp_dir, evidence_path, reviews)
        disp = self.helper.dispose(temp_dir, evidence_path, reviews)
        return fs, ev, disp

    def _clean_reviews(self):
        return [
            self.helper.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
            self.helper.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
        ]

    # ------------------------------------------------------------------
    # 13.1 positive acceptance
    # ------------------------------------------------------------------

    def test_accepted_disposition_produces_artifact(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertEqual(artifact.disposition, "ACCEPTED")
            self.assertTrue(artifact.is_accepted)

    def test_artifact_binds_correct_task(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertEqual(artifact.task_id, disp.task_id)

    def test_artifact_binds_correct_evidence_package(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            reviews_path = ev
            fs, ev_, disp = self._accepted_chain(d, reviews_path, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertEqual(artifact.evidence_package_id, disp.evidence_package_id)

    def test_artifact_binds_6a_hash(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertEqual(artifact.finding_set_sha256, fs.finding_set_sha256)

    def test_artifact_binds_6b_hash(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertEqual(artifact.evaluation_sha256, ev_.evaluation_sha256)

    def test_artifact_binds_6c_hash(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertEqual(artifact.disposition_sha256, disp.disposition_sha256)

    def test_artifact_is_immutable(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            with self.assertRaises(Exception):
                setattr(artifact, "disposition", "REJECTED")

    def test_acceptance_hash_re_derives(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            # Internal integrity: recorded hash == hash of the canonical
            # (deterministic) document. `accepted_at` is audit metadata and is
            # excluded from the hashed shape, consistent with 6B/6C.
            self.assertEqual(
                artifact.acceptance_sha256,
                sha256_payload(_acceptance_document(artifact)),
            )

    def test_acceptance_hash_pinned(self) -> None:
        """Independently re-derived and verified stable across modes."""
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertEqual(
                artifact.acceptance_sha256,
                "27d6d92feb5b87439375c6df2543dd36b469a2305a0eedbee24f284b408428fc",
            )

    def test_acceptance_validates_against_hermes_acceptance_schema(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            # The public document must satisfy the existing downstream envelope.
            t.catalog.validate("hermes.acceptance", artifact.as_document())

    # ------------------------------------------------------------------
    # 13.2 non-eligible dispositions
    # ------------------------------------------------------------------

    def test_rejected_cannot_create_acceptance(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            # Self-consistent REJECTED disposition: its own hash verifies, so the
            # only thing rejecting it is the eligibility rule.
            bad = _self_consistent_disposition(
                DISPOSITION_REJECTED,
                task_id=disp.task_id,
                evidence_package_id=disp.evidence_package_id,
                finding_set_sha256=fs.finding_set_sha256,
                evaluation_sha256=ev_.evaluation_sha256,
            )
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(bad, ev_, fs)

    def test_escalated_cannot_create_acceptance(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            bad = _self_consistent_disposition(
                DISPOSITION_ESCALATED,
                task_id=disp.task_id,
                evidence_package_id=disp.evidence_package_id,
                finding_set_sha256=fs.finding_set_sha256,
                evaluation_sha256=ev_.evaluation_sha256,
            )
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(bad, ev_, fs)

    def test_blocked_cannot_create_acceptance(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            bad = _self_consistent_disposition(
                DISPOSITION_BLOCKED,
                task_id=disp.task_id,
                evidence_package_id=disp.evidence_package_id,
                finding_set_sha256=fs.finding_set_sha256,
                evaluation_sha256=ev_.evaluation_sha256,
            )
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(bad, ev_, fs)

    def test_inconclusive_cannot_create_acceptance(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            bad = _self_consistent_disposition(
                DISPOSITION_INCONCLUSIVE,
                task_id=disp.task_id,
                evidence_package_id=disp.evidence_package_id,
                finding_set_sha256=fs.finding_set_sha256,
                evaluation_sha256=ev_.evaluation_sha256,
            )
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(bad, ev_, fs)

    # ------------------------------------------------------------------
    # 13.3 tamper rejection
    # ------------------------------------------------------------------

    def test_modified_task_id_rejected(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            bad = replace(fs, task_id="99999999-9999-9999-9999-999999999999")
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, bad)

    def test_modified_evidence_package_id_rejected(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            bad = replace(fs, evidence_package_id="other-evidence")
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, bad)

    def test_modified_finding_set_hash_rejected(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            bad = _self_consistent_finding_set(
                "0" * 64,
                task_id=fs.task_id,
                evidence_package_id=fs.evidence_package_id,
                review_ids=ev_.review_ids,
            )
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, bad)

    def test_modified_evaluation_hash_rejected(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            bad = _self_consistent_evaluation(
                "0" * 64,
                task_id=ev_.task_id,
                evidence_package_id=ev_.evidence_package_id,
                finding_set_sha256=fs.finding_set_sha256,
                review_ids=ev_.review_ids,
            )
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(disp, bad, fs)

    def test_modified_disposition_hash_rejected(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            bad = _self_consistent_disposition(
                DISPOSITION_ACCEPTED,
                task_id=disp.task_id,
                evidence_package_id=disp.evidence_package_id,
                finding_set_sha256=fs.finding_set_sha256,
                evaluation_sha256=ev_.evaluation_sha256,
            )
            # Tamper only the recorded hash; chain links stay consistent.
            bad = replace(bad, disposition_sha256="0" * 64)
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(bad, ev_, fs)

    def test_modified_disposition_rejected(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            bad = _self_consistent_disposition(
                DISPOSITION_REJECTED,
                task_id=disp.task_id,
                evidence_package_id=disp.evidence_package_id,
                finding_set_sha256=fs.finding_set_sha256,
                evaluation_sha256=ev_.evaluation_sha256,
            )
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(bad, ev_, fs)

    def test_modified_normalized_findings_rejected(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            # Tamper the evaluation's referenced finding set hash indirectly by
            # handing a disposition whose finding-set reference no longer matches.
            mismatched_fs = replace(fs, finding_set_sha256="1" * 64)
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, mismatched_fs)

    # Isolating re-verification tests: only the targeted hashed-input is wrong
    # while every cross-object chain link stays consistent, so the specific
    # re-verification guard is the sole gate (proves mutation teeth for M4/M5/M6).

    def test_evaluation_hash_reverify_isolated(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            # Tamper the evaluation's recorded hash AND align the disposition's
            # evaluation reference to the same wrong value, so the chain link
            # holds; only the evaluation's own-hash re-verification is violated.
            wrong = "a" * 64
            bad_ev = _self_consistent_evaluation(wrong, task_id=ev_.task_id, evidence_package_id=ev_.evidence_package_id, finding_set_sha256=fs.finding_set_sha256, review_ids=ev_.review_ids)
            bad_disp = _self_consistent_disposition(DISPOSITION_ACCEPTED, task_id=disp.task_id, evidence_package_id=disp.evidence_package_id, finding_set_sha256=fs.finding_set_sha256, evaluation_sha256=wrong)
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(bad_disp, bad_ev, fs)

    def test_finding_set_hash_reverify_isolated(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            wrong = "b" * 64
            # Tamper the finding-set recorded hash AND align the evaluation and
            # disposition references to the same wrong value, so the only
            # violated check is the finding-set's own-hash re-verification.
            bad_fs = _self_consistent_finding_set(wrong, task_id=fs.task_id, evidence_package_id=fs.evidence_package_id, review_ids=ev_.review_ids)
            bad_ev = _self_consistent_evaluation(None, task_id=ev_.task_id, evidence_package_id=ev_.evidence_package_id, finding_set_sha256=wrong, review_ids=ev_.review_ids)
            bad_disp = _self_consistent_disposition(DISPOSITION_ACCEPTED, task_id=disp.task_id, evidence_package_id=disp.evidence_package_id, finding_set_sha256=wrong, evaluation_sha256=bad_ev.evaluation_sha256)
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(bad_disp, bad_ev, bad_fs)

    def test_evidence_binding_reverify_isolated(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            # Self-consistent finding set under a different evidence_package_id,
            # with the disposition/evaluation references aligned to its hash. The
            # only violated invariant is the shared evidence_package_id binding.
            bad_fs = _self_consistent_finding_set(None, task_id=fs.task_id, evidence_package_id="other-evidence", review_ids=ev_.review_ids)
            bad_ev = _self_consistent_evaluation(None, task_id=ev_.task_id, evidence_package_id=ev_.evidence_package_id, finding_set_sha256=bad_fs.finding_set_sha256, review_ids=ev_.review_ids)
            bad_disp = _self_consistent_disposition(DISPOSITION_ACCEPTED, task_id=disp.task_id, evidence_package_id=disp.evidence_package_id, finding_set_sha256=bad_fs.finding_set_sha256, evaluation_sha256=bad_ev.evaluation_sha256)
            with self.assertRaises(AcceptanceArtifactError):
                AcceptanceArtifactBuilder(t.catalog).build(bad_disp, bad_ev, bad_fs)

    # ------------------------------------------------------------------
    # 13.4 determinism
    # ------------------------------------------------------------------

    def test_repeated_builds_identical(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            a1 = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            a2 = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertEqual(a1.acceptance_sha256, a2.acceptance_sha256)
            self.assertEqual(a1.acceptance_id, a2.acceptance_id)

    def test_acceptance_id_deterministic(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertTrue(artifact.acceptance_id.startswith("acceptance-"))
            self.assertEqual(len(artifact.acceptance_id), len("acceptance-") + 16)

    def test_review_ordering_irrelevant(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            r1 = t.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            r2 = t.review(REVIEW_TWO, agent_id="reviewer-2", findings=[])
            fs_a, ev_a, disp_a = self._accepted_chain(d, ev, [r1, r2])
            fs_b, ev_b, disp_b = self._accepted_chain(d, ev, [r2, r1])
            a1 = AcceptanceArtifactBuilder(t.catalog).build(disp_a, ev_a, fs_a)
            a2 = AcceptanceArtifactBuilder(t.catalog).build(disp_b, ev_b, fs_b)
            self.assertEqual(a1.acceptance_sha256, a2.acceptance_sha256)

    # ------------------------------------------------------------------
    # 13.5 traceability
    # ------------------------------------------------------------------

    def test_review_and_finding_references_preserved(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            self.assertEqual(set(artifact.review_ids), {REVIEW_ONE, REVIEW_TWO})
            self.assertEqual(tuple(sorted(artifact.finding_keys)), tuple(sorted(f.finding_key for f in fs.findings)))
            self.assertEqual(artifact.consensus_id, disp.disposition_sha256)

    # ------------------------------------------------------------------
    # 13.6 immutability
    # ------------------------------------------------------------------

    def test_nested_collections_immutable(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            with self.assertRaises(Exception):
                artifact.reason_codes.append("x")
            with self.assertRaises(Exception):
                artifact.review_ids.append("y")

    # ------------------------------------------------------------------
    # 13.7 non-authority
    # ------------------------------------------------------------------

    def test_no_prohibited_authority_keys(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            artifact = AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            doc = artifact.as_document()
            self.assertNotIn("execution_authorization", doc)
            self.assertNotIn("state_transition", doc)
            self.assertNotIn("ledger_sequence", doc)
            self.assertNotIn("database_row_id", doc)
            self.assertFalse(artifact.authority.get("can_authorize_execution"))
            self.assertTrue(artifact.authority.get("requires_separate_authorization"))

    # ------------------------------------------------------------------
    # 13.8 side effects
    # ------------------------------------------------------------------

    def test_no_filesystem_writes(self) -> None:
        t = mod.HermesConsensusDispositionTests()
        with tempfile.TemporaryDirectory() as d:
            ev = self.helper.freeze_fixture(d)
            reviews = self._clean_reviews()
            fs, ev_, disp = self._accepted_chain(d, ev, reviews)
            before = sorted(Path(d).iterdir())
            AcceptanceArtifactBuilder(t.catalog).build(disp, ev_, fs)
            after = sorted(Path(d).iterdir())
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
