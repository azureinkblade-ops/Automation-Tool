from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    ConsensusDisposition,
    ConsensusDispositionEngine,
    ConsensusDispositionError,
    ConsensusEvaluation,
    FindingNormalizer,
    load_schema_catalog,
    sha256_payload,
)
from tools.hermes_core.consensus_disposition import (
    BLOCKING_SEVERITIES,
    DISPOSITION_ACCEPTED,
    DISPOSITION_BLOCKED,
    DISPOSITION_ESCALATED,
    DISPOSITION_INCONCLUSIVE,
    DISPOSITION_REJECTED,
    REASON_CONFIDENCE_THRESHOLD_NOT_DEFINED,
    REASON_CRITICAL_FINDING_PRESENT,
    REASON_DETERMINISTIC_FAILURE,
    REASON_HIGH_FINDING_PRESENT,
    REASON_LOWER_SEVERITY_POLICY_RESOLVED,
    REASON_MATERIAL_DISAGREEMENT,
    REASON_UNANIMOUS_CLEAN,
    REASON_UNANIMOUS_FINDING,
    REASON_UNANIMOUS_RECOMMENDATION,
)
from tools.hermes_core.consensus_evaluator import (
    ConsensusEvaluator,
    MATERIAL_DISAGREEMENT,
    UNANIMOUS_CLEAN,
    UNANIMOUS_FINDING,
    DETERMINISTIC_FAILURE,
)

TASK_ID = "11111111-1111-1111-1111-111111111111"
REVIEW_ONE = "22222222-2222-2222-2222-222222222222"
REVIEW_TWO = "33333333-3333-3333-3333-333333333333"
REVIEW_THREE = "44444444-4444-4444-4444-444444444444"
OTHER_TASK_ID = "55555555-5555-5555-5555-555555555555"
EVIDENCE_PACKAGE_ID = "evidence-consensus-disposition-fixture"


class HermesConsensusDispositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    # ------------------------------------------------------------------
    # fixtures
    # ------------------------------------------------------------------

    def freeze_fixture(self, temp_dir: str) -> Path:
        base_dir = Path(temp_dir)
        (base_dir / "artifact_a.txt").write_text("evidence a", encoding="utf-8")
        (base_dir / "artifact_b.txt").write_text("evidence b", encoding="utf-8")
        from tools.hermes_core import EvidencePackageBuilder

        builder = EvidencePackageBuilder(self.catalog, base_dir=base_dir)
        builder.freeze_to_file(
            base_dir / "evidence.json",
            task_id=TASK_ID,
            artifacts=["artifact_a.txt", "artifact_b.txt"],
            evidence_package_id=EVIDENCE_PACKAGE_ID,
            created_at="2026-08-11T10:00:00Z",
        )
        return base_dir / "evidence.json"

    def artifact_ids(self, evidence_path: Path) -> list[str]:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        return [item["artifact_id"] for item in evidence["inventory"]]

    def review(
        self,
        review_id: str,
        *,
        agent_id: str,
        findings: list[dict],
        recommendation: str = "accept",
    ) -> dict:
        return {
            "review_id": review_id,
            "task_id": TASK_ID,
            "evidence_package_id": EVIDENCE_PACKAGE_ID,
            "reviewer": {
                "agent_id": agent_id,
                "model_id": "local-model",
                "role": "architect_reviewer",
            },
            "started_at": "2026-08-11T10:05:00Z",
            "completed_at": "2026-08-11T10:06:00Z",
            "findings": findings,
            "recommendation": recommendation,
            "authority": {
                "can_modify_state": False,
                "can_authorize_execution": False,
                "can_execute": False,
            },
        }

    def finding(
        self,
        finding_id: str,
        *,
        severity: str = "high",
        summary: str = "Unbounded retry loop in the worker path.",
        evidence_refs: list[str] | None = None,
        confidence: float = 0.8,
    ) -> dict:
        return {
            "finding_id": finding_id,
            "severity": severity,
            "summary": summary,
            "evidence_refs": evidence_refs or [],
            "confidence": confidence,
        }

    def evaluation(
        self,
        temp_dir: str,
        evidence_path: Path,
        reviews: list[dict],
        *,
        expected_review_count: int | None = None,
    ) -> ConsensusEvaluation:
        finding_set = FindingNormalizer(self.catalog, base_dir=temp_dir).normalize(
            reviews, evidence_path=evidence_path
        )
        return ConsensusEvaluator(self.catalog, base_dir=temp_dir).evaluate(
            finding_set,
            reviews,
            evidence_path=evidence_path,
            expected_review_count=expected_review_count,
        )

    def finding_set(
        self,
        temp_dir: str,
        evidence_path: Path,
        reviews: list[dict],
    ):
        return FindingNormalizer(self.catalog, base_dir=temp_dir).normalize(
            reviews, evidence_path=evidence_path
        )

    def dispose(
        self,
        temp_dir: str,
        evidence_path: Path,
        reviews: list[dict],
        *,
        expected_review_count: int | None = None,
        override_finding_set=None,
        override_evaluation=None,
    ) -> ConsensusDisposition:
        fs = override_finding_set or self.finding_set(temp_dir, evidence_path, reviews)
        ev = override_evaluation or self.evaluation(
            temp_dir, evidence_path, reviews, expected_review_count=expected_review_count
        )
        return ConsensusDispositionEngine(self.catalog, base_dir=temp_dir).dispose(
            ev, fs, expected_review_count=expected_review_count
        )

    # ------------------------------------------------------------------
    # 13.1 deterministic failure
    # ------------------------------------------------------------------

    def test_deterministic_failure_maps_to_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            disposition = self.dispose(
                temp_dir, evidence_path, reviews, expected_review_count=3
            )

            self.assertEqual(disposition.disposition, DISPOSITION_BLOCKED)
            self.assertEqual(disposition.agreement_class, DETERMINISTIC_FAILURE)

    def test_deterministic_failure_preserves_evaluation_reason_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            disposition = self.dispose(
                temp_dir, evidence_path, reviews, expected_review_count=3
            )

            self.assertIn(REASON_DETERMINISTIC_FAILURE, disposition.reason_codes)
            # original 6B failure reason preserved
            self.assertIn("missing_required_review", disposition.reason_codes)

    def test_deterministic_failure_emits_no_acceptance_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            document = self.dispose(
                temp_dir, evidence_path, reviews, expected_review_count=3
            ).as_document()

            for forbidden in (
                "acceptance",
                "acceptance_artifact",
                "authorization",
                "ledger",
                "state",
                "can_execute",
                "can_authorize_execution",
                "rationale",
                "consensus_id",
            ):
                self.assertNotIn(forbidden, document)

    # ------------------------------------------------------------------
    # 13.2 material disagreement
    # ------------------------------------------------------------------

    def test_material_disagreement_maps_to_escalated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)

            self.assertEqual(disposition.disposition, DISPOSITION_ESCALATED)
            self.assertEqual(disposition.agreement_class, MATERIAL_DISAGREEMENT)

    def test_recommendation_conflict_maps_to_escalated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                    recommendation="accept",
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-777", evidence_refs=[artifact_a])],
                    recommendation="reject",
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)

            self.assertEqual(disposition.disposition, DISPOSITION_ESCALATED)
            self.assertIn(REASON_MATERIAL_DISAGREEMENT, disposition.reason_codes)
            self.assertIn("recommendation_conflict", disposition.reason_codes)

    def test_finding_coverage_conflict_maps_to_escalated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a], severity="critical")],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-002", evidence_refs=[artifact_b], severity="low")],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)

            self.assertEqual(disposition.disposition, DISPOSITION_ESCALATED)

    def test_escalation_preserves_per_finding_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            evaluation = self.evaluation(temp_dir, evidence_path, reviews)
            disposition = ConsensusDispositionEngine(self.catalog).dispose(
                evaluation, self.finding_set(temp_dir, evidence_path, reviews)
            )

            # 6B finding coverage is still available on the evaluation, unchanged
            self.assertTrue(len(evaluation.finding_agreements) >= 1)
            self.assertFalse(evaluation.finding_agreements[0].unanimous)

    def test_escalation_does_not_pick_a_winning_reviewer(self) -> None:
        """Escalation must not decide which reviewer is correct (no adjudication)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            document = self.dispose(temp_dir, evidence_path, reviews).as_document()

            # no field names an adjudicated winner or a majority decision
            for forbidden in ("winner", "majority", "adjudicat", "override"):
                self.assertNotIn(forbidden, str(document).lower())

    def test_escalation_no_majority_vote_shortcut(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            evaluation = self.evaluation(temp_dir, evidence_path, reviews)
            disposition = ConsensusDispositionEngine(self.catalog).dispose(
                evaluation, self.finding_set(temp_dir, evidence_path, reviews)
            )
            # A 1-vs-1 split must not become ACCEPTED/REJECTED via a vote count.
            self.assertEqual(disposition.disposition, DISPOSITION_ESCALATED)
            self.assertNotIn("majority", str(disposition.reason_codes).lower())

    # ------------------------------------------------------------------
    # 13.3 unanimous clean
    # ------------------------------------------------------------------

    def test_unanimous_clean_accept_maps_to_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)

            self.assertEqual(disposition.disposition, DISPOSITION_ACCEPTED)
            self.assertEqual(disposition.agreement_class, UNANIMOUS_CLEAN)
            self.assertIn(REASON_UNANIMOUS_RECOMMENDATION, disposition.reason_codes)

    def test_unanimous_clean_no_findings_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.relevant_finding_keys, ())
            self.assertEqual(disposition.blocking_finding_keys, ())

    def test_unanimous_clean_reject_maps_to_rejected_not_accepted(self) -> None:
        """ACCEPTED is not automatic; a unanimous reject must yield REJECTED."""
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[], recommendation="reject"),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[], recommendation="reject"),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_REJECTED)
            self.assertFalse(disposition.is_accepted)

    def test_unanimous_clean_escalate_maps_to_escalated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[], recommendation="escalate"),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[], recommendation="escalate"),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_ESCALATED)

    def test_unanimous_clean_inconclusive_maps_to_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[], recommendation="inconclusive"),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[], recommendation="inconclusive"),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_INCONCLUSIVE)

    def test_accepted_disposition_does_not_grant_execution_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            document = self.dispose(temp_dir, evidence_path, reviews).as_document()
            for forbidden in ("authorization", "can_execute", "can_authorize_execution", "authority"):
                self.assertNotIn(forbidden, document)

    # ------------------------------------------------------------------
    # 13.4 critical/high blocking
    # ------------------------------------------------------------------

    def test_unanimous_critical_finding_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", severity="critical", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-777", severity="critical", evidence_refs=[artifact_a])],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)

            self.assertEqual(disposition.disposition, DISPOSITION_BLOCKED)
            self.assertIn(REASON_CRITICAL_FINDING_PRESENT, disposition.reason_codes)
            self.assertEqual(disposition.blocking_severities, ("critical",))

    def test_unanimous_high_finding_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", severity="high", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-777", severity="high", evidence_refs=[artifact_a])],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)

            self.assertEqual(disposition.disposition, DISPOSITION_BLOCKED)
            self.assertIn(REASON_HIGH_FINDING_PRESENT, disposition.reason_codes)
            self.assertEqual(disposition.blocking_severities, ("high",))

    def test_multiple_findings_including_critical_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[
                        self.finding("F-001", severity="critical", evidence_refs=[artifact_a]),
                        self.finding("F-002", severity="low", evidence_refs=[artifact_b]),
                    ],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[
                        self.finding("F-777", severity="critical", evidence_refs=[artifact_a]),
                        self.finding("F-888", severity="low", evidence_refs=[artifact_b]),
                    ],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_BLOCKED)
            self.assertEqual(disposition.blocking_severities, ("critical",))
            self.assertIn(REASON_CRITICAL_FINDING_PRESENT, disposition.reason_codes)

    def test_multiple_findings_including_high_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[
                        self.finding("F-001", severity="high", evidence_refs=[artifact_a]),
                        self.finding("F-002", severity="low", evidence_refs=[artifact_b]),
                    ],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[
                        self.finding("F-777", severity="high", evidence_refs=[artifact_a]),
                        self.finding("F-888", severity="low", evidence_refs=[artifact_b]),
                    ],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_BLOCKED)
            self.assertEqual(disposition.blocking_severities, ("high",))

    def test_finding_order_cannot_affect_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            first = [
                self.finding("F-001", severity="high", evidence_refs=[artifact_a]),
                self.finding("F-002", severity="low", evidence_refs=[artifact_b]),
            ]
            second = list(reversed(first))

            d1 = self.dispose(
                temp_dir,
                evidence_path,
                [self.review(REVIEW_ONE, agent_id="reviewer-1", findings=first),
                 self.review(REVIEW_TWO, agent_id="reviewer-2", findings=first)],
            )
            d2 = self.dispose(
                temp_dir,
                evidence_path,
                [self.review(REVIEW_ONE, agent_id="reviewer-1", findings=second),
                 self.review(REVIEW_TWO, agent_id="reviewer-2", findings=second)],
            )
            self.assertEqual(d1.as_document(), d2.as_document())
            self.assertEqual(d1.disposition_sha256, d2.disposition_sha256)

    def test_critical_high_blocking_reason_codes_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            # Both reviewers report the same two findings (critical + high) so the
            # agreement class is unanimous_finding, exercising both blocking rules.
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[
                        self.finding("F-001", severity="critical", evidence_refs=[artifact_a]),
                        self.finding("F-002", severity="high", evidence_refs=[artifact_a]),
                    ],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[
                        self.finding("F-001", severity="critical", evidence_refs=[artifact_a]),
                        self.finding("F-002", severity="high", evidence_refs=[artifact_a]),
                    ],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_BLOCKED)
            self.assertEqual(disposition.blocking_severities, ("critical", "high"))
            self.assertIn(REASON_CRITICAL_FINDING_PRESENT, disposition.reason_codes)
            self.assertIn(REASON_HIGH_FINDING_PRESENT, disposition.reason_codes)
            self.assertEqual(disposition.agreement_class, UNANIMOUS_FINDING)

    # ------------------------------------------------------------------
    # 13.5 lower-severity policy
    # ------------------------------------------------------------------

    def test_medium_only_finding_follows_recommendation(self) -> None:
        """Medium is not in BLOCKING_SEVERITIES, so it follows the unanimous recommendation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            # identical finding content across reviewers -> unanimous_finding
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", severity="medium", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-001", severity="medium", evidence_refs=[artifact_a])],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_ACCEPTED)
            self.assertIn(REASON_LOWER_SEVERITY_POLICY_RESOLVED, disposition.reason_codes)
            self.assertEqual(disposition.blocking_finding_keys, ())
            self.assertEqual(disposition.agreement_class, UNANIMOUS_FINDING)

    def test_low_only_finding_follows_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", severity="low", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-001", severity="low", evidence_refs=[artifact_a])],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_ACCEPTED)
            self.assertIn(REASON_LOWER_SEVERITY_POLICY_RESOLVED, disposition.reason_codes)

    def test_info_only_finding_follows_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", severity="info", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-001", severity="info", evidence_refs=[artifact_a])],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_ACCEPTED)
            self.assertIn(REASON_LOWER_SEVERITY_POLICY_RESOLVED, disposition.reason_codes)

    def test_mixed_medium_low_info_follows_recommendation(self) -> None:
        """Two identical-content findings, each below the blocking threshold.

        Both reviewers must report the same severity per finding; differing
        severity on the same finding is a 6A material disagreement, not a
        unanimous finding.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[
                        self.finding("F-001", severity="medium", evidence_refs=[artifact_a]),
                        self.finding("F-002", severity="low", evidence_refs=[artifact_b]),
                    ],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[
                        self.finding("F-001", severity="medium", evidence_refs=[artifact_a]),
                        self.finding("F-002", severity="low", evidence_refs=[artifact_b]),
                    ],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.disposition, DISPOSITION_ACCEPTED)
            self.assertEqual(disposition.blocking_finding_keys, ())
            self.assertIn(REASON_LOWER_SEVERITY_POLICY_RESOLVED, disposition.reason_codes)
            self.assertEqual(disposition.agreement_class, UNANIMOUS_FINDING)

    def test_blocking_set_is_exactly_critical_high(self) -> None:
        self.assertEqual(BLOCKING_SEVERITIES, frozenset({"critical", "high"}))

    # ------------------------------------------------------------------
    # 13.6 confidence
    # ------------------------------------------------------------------

    def test_confidence_values_do_not_change_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            low_conf = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                recommendation="accept",
                findings=[self.finding("F-001", severity="low", evidence_refs=[artifact_a], confidence=0.05)],
            )
            high_conf = self.review(
                REVIEW_TWO,
                agent_id="reviewer-2",
                recommendation="accept",
                findings=[self.finding("F-001", severity="low", evidence_refs=[artifact_a], confidence=0.99)],
            )
            disposition = self.dispose(temp_dir, evidence_path, [low_conf, high_conf])
            # low confidence must NOT be treated as failure, and identical findings
            # make this unanimous_finding (not material_disagreement)
            self.assertEqual(disposition.disposition, DISPOSITION_ACCEPTED)
            self.assertEqual(disposition.agreement_class, UNANIMOUS_FINDING)

    def test_no_hidden_numeric_threshold_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[], recommendation="accept"),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[], recommendation="accept"),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            marker = disposition.confidence_policy_marker
            self.assertFalse(marker["enforced"])
            self.assertEqual(marker["reason"], "numeric_threshold_not_defined")
            self.assertIn(REASON_CONFIDENCE_THRESHOLD_NOT_DEFINED, disposition.reason_codes)

    def test_confidence_remains_auditable_in_finding_set(self) -> None:
        """Confidence must stay traceable through the normalized finding set."""
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", severity="low", evidence_refs=[artifact_a], confidence=0.37)],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-001", severity="low", evidence_refs=[artifact_a], confidence=0.42)],
                ),
            ]
            fs = self.finding_set(temp_dir, evidence_path, reviews)
            confidences = sorted(
                source.confidence for finding in fs.findings for source in finding.sources
            )
            self.assertEqual(confidences, [0.37, 0.42])

    # ------------------------------------------------------------------
    # 13.7 binding / tamper
    # ------------------------------------------------------------------

    def test_wrong_task_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            fs = self.finding_set(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            ev = self.evaluation(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            bad_fs = dataclasses.replace(fs, task_id=OTHER_TASK_ID)
            with self.assertRaises(ConsensusDispositionError):
                ConsensusDispositionEngine(self.catalog).dispose(ev, bad_fs)

    def test_wrong_evidence_package_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            fs = self.finding_set(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            ev = self.evaluation(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            bad_fs = dataclasses.replace(fs, evidence_package_id="other-package")
            with self.assertRaises(ConsensusDispositionError):
                ConsensusDispositionEngine(self.catalog).dispose(ev, bad_fs)

    def test_wrong_finding_set_sha256_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            fs = self.finding_set(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            ev = self.evaluation(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            bad_fs = dataclasses.replace(fs, finding_set_sha256="deadbeef")
            with self.assertRaises(ConsensusDispositionError):
                ConsensusDispositionEngine(self.catalog).dispose(ev, bad_fs)

    def test_wrong_evaluation_sha256_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            fs = self.finding_set(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            ev = self.evaluation(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            bad_ev = dataclasses.replace(ev, evaluation_sha256="deadbeef")
            with self.assertRaises(ConsensusDispositionError):
                ConsensusDispositionEngine(self.catalog).dispose(bad_ev, fs)

    def test_mutated_normalized_finding_set_rejected(self) -> None:
        """If the finding set is hand-mutated so its hash no longer verifies, 6C must refuse."""
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            fs = self.finding_set(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            # recompute a wrong hash: tamper then recompute won't match the stored value
            import hashlib
            from tools.hermes_core.hashing import sha256_payload

            wrong = dataclasses.replace(fs, finding_set_sha256=sha256_payload({"tampered": True}))
            ev = self.evaluation(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            with self.assertRaises(ConsensusDispositionError):
                ConsensusDispositionEngine(self.catalog).dispose(ev, wrong)

    def test_mutated_evaluation_document_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            fs = self.finding_set(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            ev = self.evaluation(temp_dir, evidence_path, [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ])
            bad_ev = dataclasses.replace(
                ev, agreement_class="unanimous_finding", evaluation_sha256=ev.evaluation_sha256
            )
            with self.assertRaises(ConsensusDispositionError):
                ConsensusDispositionEngine(self.catalog).dispose(bad_ev, fs)

    def test_expected_review_count_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            fs = self.finding_set(temp_dir, evidence_path, reviews)
            ev = self.evaluation(temp_dir, evidence_path, reviews, expected_review_count=2)
            with self.assertRaises(ConsensusDispositionError):
                ConsensusDispositionEngine(self.catalog).dispose(ev, fs, expected_review_count=3)

    def test_invalid_inputs_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            fs = self.finding_set(temp_dir, evidence_path, reviews)
            ev = self.evaluation(temp_dir, evidence_path, reviews)
            for label, call in [
                ("non-evaluation", lambda: ConsensusDispositionEngine(self.catalog).dispose(fs, fs)),
                ("non-finding-set", lambda: ConsensusDispositionEngine(self.catalog).dispose(ev, ev)),
            ]:
                with self.subTest(label=label):
                    with self.assertRaises(ConsensusDispositionError):
                        call()

    # ------------------------------------------------------------------
    # 13.8 determinism
    # ------------------------------------------------------------------

    def test_repeated_execution_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            first = self.dispose(temp_dir, evidence_path, reviews)
            second = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(first.as_document(), second.as_document())
            self.assertEqual(first.disposition_sha256, second.disposition_sha256)

    def test_reason_code_order_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", severity="critical", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-777", severity="critical", evidence_refs=[artifact_a])],
                ),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertEqual(disposition.reason_codes, tuple(sorted(disposition.reason_codes)))

    def test_review_order_irrelevant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", severity="high", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-001", severity="high", evidence_refs=[artifact_a])],
                ),
            ]
            forward = self.dispose(temp_dir, evidence_path, reviews)
            reverse = self.dispose(temp_dir, evidence_path, list(reversed(reviews)))
            self.assertEqual(forward.as_document(), reverse.as_document())
            self.assertEqual(forward.disposition_sha256, reverse.disposition_sha256)

    def test_disposition_hash_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            # Internal integrity: the recorded hash must equal the hash of the
            # canonical document minus the hash field itself.
            document = disposition.as_document()
            recorded_hash = document.pop("disposition_sha256")
            self.assertEqual(recorded_hash, sha256_payload(document))
            # Cross-context pin: the canonical disposition hash is independently
            # re-derived and verified stable across direct/helper/unittest modes.
            self.assertEqual(
                disposition.disposition_sha256,
                "106eb0d20d483d94e1a56f7209b5643ea153e281f560b5066b33ecf629deba8f",
            )

    # ------------------------------------------------------------------
    # 13.9 immutability
    # ------------------------------------------------------------------

    def test_result_is_frozen_and_nested_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                disposition.disposition = DISPOSITION_BLOCKED  # type: ignore[misc]
            with self.assertRaises(dataclasses.FrozenInstanceError):
                disposition.reason_codes = ()  # type: ignore[misc]
            self.assertIsInstance(disposition.reason_codes, tuple)
            self.assertIsInstance(disposition.relevant_finding_keys, tuple)
            self.assertIsInstance(disposition.blocking_finding_keys, tuple)
            self.assertIsInstance(disposition.blocking_severities, tuple)

    # ------------------------------------------------------------------
    # 13.10 non-authority / side effects
    # ------------------------------------------------------------------

    def test_no_filesystem_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            base_dir = Path(temp_dir)
            before = {
                path.relative_to(base_dir).as_posix(): path.stat().st_mtime_ns
                for path in sorted(base_dir.rglob("*"))
                if path.is_file()
            }
            self.dispose(temp_dir, evidence_path, reviews)
            after = {
                path.relative_to(base_dir).as_posix(): path.stat().st_mtime_ns
                for path in sorted(base_dir.rglob("*"))
                if path.is_file()
            }
            self.assertEqual(before, after)

    def test_no_prohibited_authority_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            document = self.dispose(temp_dir, evidence_path, reviews).as_document()
            banned = {
                "ledger", "state", "authorization", "acceptance",
                "can_execute", "can_authorize_execution", "consensus_id",
                "adjudicator", "rationale",
            }
            self.assertFalse(set(document) & banned)

    def test_disposition_is_not_a_terminal_execution_authorization(self) -> None:
        """Accepted != permitted to execute; disposition vocabulary is not 6E's."""
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]
            disposition = self.dispose(temp_dir, evidence_path, reviews)
            self.assertTrue(disposition.is_accepted)
            document = disposition.as_document()
            # 6E transition names must not appear
            self.assertNotIn("AWAITING_EXECUTION_AUTHORIZATION", str(document))
            self.assertNotIn("ACCEPTED".lower(), str(document).lower().split("disposition")[1] if "disposition" in str(document).lower() else "")


if __name__ == "__main__":
    unittest.main()
