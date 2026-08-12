from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    ConsensusEvaluationError,
    ConsensusEvaluator,
    EvidencePackageBuilder,
    FindingNormalizer,
    load_schema_catalog,
)
from tools.hermes_core.consensus_evaluator import (
    DETERMINISTIC_FAILURE,
    MATERIAL_DISAGREEMENT,
    REASON_DUPLICATE_REVIEW_ID,
    REASON_DUPLICATE_REVIEWER_IDENTITY,
    REASON_EVIDENCE_PACKAGE_MISMATCH,
    REASON_FINDING_COVERAGE_CONFLICT,
    REASON_FINDING_SET_HASH_MISMATCH,
    REASON_INVALID_REVIEW_REPORT,
    REASON_MISSING_REQUIRED_REVIEW,
    REASON_RECOMMENDATION_CONFLICT,
    REASON_REVIEW_ID_MISMATCH,
    REASON_TASK_ID_MISMATCH,
    UNANIMOUS_CLEAN,
    UNANIMOUS_FINDING,
)

TASK_ID = "11111111-1111-1111-1111-111111111111"
REVIEW_ONE = "22222222-2222-2222-2222-222222222222"
REVIEW_TWO = "33333333-3333-3333-3333-333333333333"
REVIEW_THREE = "44444444-4444-4444-4444-444444444444"
OTHER_TASK_ID = "55555555-5555-5555-5555-555555555555"
EVIDENCE_PACKAGE_ID = "evidence-consensus-fixture"


class HermesConsensusEvaluatorTests(unittest.TestCase):
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
        role: str = "architect_reviewer",
    ) -> dict:
        return {
            "review_id": review_id,
            "task_id": TASK_ID,
            "evidence_package_id": EVIDENCE_PACKAGE_ID,
            "reviewer": {
                "agent_id": agent_id,
                "model_id": "local-model",
                "role": role,
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

    def normalizer(self, temp_dir: str) -> FindingNormalizer:
        return FindingNormalizer(self.catalog, base_dir=temp_dir)

    def evaluator(self, temp_dir: str) -> ConsensusEvaluator:
        return ConsensusEvaluator(self.catalog, base_dir=temp_dir)

    def evaluate(
        self,
        temp_dir: str,
        evidence_path: Path,
        reviews: list[dict],
        *,
        expected_review_count: int | None = None,
    ):
        finding_set = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)
        return self.evaluator(temp_dir).evaluate(
            finding_set,
            reviews,
            evidence_path=evidence_path,
            expected_review_count=expected_review_count,
        )

    # ------------------------------------------------------------------
    # 12.1 positive agreement
    # ------------------------------------------------------------------

    def test_all_required_reviewers_clean_is_unanimous_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
                self.review(REVIEW_THREE, agent_id="reviewer-3", findings=[]),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews, expected_review_count=3)

            self.assertEqual(result.agreement_class, UNANIMOUS_CLEAN)
            self.assertEqual(result.reason_codes, ())
            self.assertEqual(result.finding_agreements, ())
            self.assertEqual(result.recommendations, ("accept",))
            self.assertFalse(result.recommendation_conflict)
            self.assertTrue(result.agreed)

    def test_same_finding_from_all_reviewers_is_unanimous_finding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-777", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_THREE,
                    agent_id="reviewer-3",
                    findings=[self.finding("OTHER", evidence_refs=[artifact_a])],
                ),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews, expected_review_count=3)

            self.assertEqual(result.agreement_class, UNANIMOUS_FINDING)
            self.assertEqual(result.reason_codes, ())
            self.assertEqual(len(result.finding_agreements), 1)
            agreement = result.finding_agreements[0]
            self.assertTrue(agreement.unanimous)
            self.assertEqual(
                agreement.reporting_review_ids,
                (REVIEW_ONE, REVIEW_TWO, REVIEW_THREE),
            )
            self.assertEqual(agreement.silent_review_ids, ())

    def test_report_order_does_not_change_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            first = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=[artifact_a])],
            )
            second = self.review(
                REVIEW_TWO,
                agent_id="reviewer-2",
                findings=[self.finding("F-002", evidence_refs=[artifact_a])],
            )

            forward = self.evaluate(temp_dir, evidence_path, [first, second])
            reverse = self.evaluate(temp_dir, evidence_path, [second, first])

            self.assertEqual(forward.as_document(), reverse.as_document())
            self.assertEqual(forward.evaluation_sha256, reverse.evaluation_sha256)

    def test_finding_order_within_a_report_does_not_change_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            one = self.finding("F-001", evidence_refs=[artifact_a])
            two = self.finding(
                "F-002",
                severity="critical",
                summary="Credential written to disk.",
                evidence_refs=[artifact_b],
            )

            forward = self.evaluate(
                temp_dir,
                evidence_path,
                [self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[one, two])],
            )
            reverse = self.evaluate(
                temp_dir,
                evidence_path,
                [self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[two, one])],
            )

            self.assertEqual(forward.as_document(), reverse.as_document())
            self.assertEqual(forward.evaluation_sha256, reverse.evaluation_sha256)

    def test_reviewer_order_does_not_change_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    review_id,
                    agent_id=agent_id,
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                )
                for review_id, agent_id in (
                    (REVIEW_ONE, "reviewer-1"),
                    (REVIEW_TWO, "reviewer-2"),
                    (REVIEW_THREE, "reviewer-3"),
                )
            ]

            forward = self.evaluate(temp_dir, evidence_path, reviews)
            shuffled = self.evaluate(temp_dir, evidence_path, list(reversed(reviews)))

            self.assertEqual(forward.as_document(), shuffled.as_document())
            self.assertEqual(forward.evaluation_sha256, shuffled.evaluation_sha256)

    def test_repeat_execution_is_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                )
            ]

            first = self.evaluate(temp_dir, evidence_path, reviews)
            second = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(first.as_document(), second.as_document())
            self.assertEqual(first.evaluation_sha256, second.evaluation_sha256)

    # ------------------------------------------------------------------
    # 12.2 recommendation conflict
    # ------------------------------------------------------------------

    def test_same_finding_same_recommendation_agrees(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                    recommendation="reject",
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-002", evidence_refs=[artifact_a])],
                    recommendation="reject",
                ),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, UNANIMOUS_FINDING)
            self.assertFalse(result.recommendation_conflict)
            self.assertEqual(result.recommendations, ("reject",))

    def test_same_finding_conflicting_recommendation_is_material_disagreement(self) -> None:
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
                    findings=[self.finding("F-002", evidence_refs=[artifact_a])],
                    recommendation="reject",
                ),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, MATERIAL_DISAGREEMENT)
            self.assertIn(REASON_RECOMMENDATION_CONFLICT, result.reason_codes)
            self.assertTrue(result.recommendation_conflict)
            self.assertFalse(result.agreed)
            # coverage itself is unanimous; only the recommendation conflicts
            self.assertNotIn(REASON_FINDING_COVERAGE_CONFLICT, result.reason_codes)

    def test_recommendation_conflict_remains_traceable_to_source_reviews(self) -> None:
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
                    findings=[self.finding("F-002", evidence_refs=[artifact_a])],
                    recommendation="escalate",
                ),
            ]
            finding_set = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)

            result = self.evaluator(temp_dir).evaluate(
                finding_set, reviews, evidence_path=evidence_path
            )

            self.assertEqual(result.recommendations, ("accept", "escalate"))
            # the normalized set still carries which review said what
            sources = {s.review_id: s.recommendation for s in finding_set.findings[0].sources}
            self.assertEqual(sources[REVIEW_ONE], "accept")
            self.assertEqual(sources[REVIEW_TWO], "escalate")

    def test_unanimous_inconclusive_is_not_converted_to_pass_or_fail(self) -> None:
        """`inconclusive` is a permitted enum value and must not be reinterpreted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(
                    REVIEW_ONE, agent_id="reviewer-1", findings=[], recommendation="inconclusive"
                ),
                self.review(
                    REVIEW_TWO, agent_id="reviewer-2", findings=[], recommendation="inconclusive"
                ),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            # Agreement class reflects input shape only; the recommendation is
            # carried forward untouched for 6C to map.
            self.assertEqual(result.agreement_class, UNANIMOUS_CLEAN)
            self.assertEqual(result.recommendations, ("inconclusive",))
            self.assertFalse(result.recommendation_conflict)

    def test_every_distinct_recommendation_pair_conflicts(self) -> None:
        pairs = [
            ("accept", "reject"),
            ("accept", "inconclusive"),
            ("accept", "escalate"),
            ("reject", "inconclusive"),
            ("reject", "escalate"),
            ("inconclusive", "escalate"),
        ]
        for first, second in pairs:
            with self.subTest(first=first, second=second):
                with tempfile.TemporaryDirectory() as temp_dir:
                    evidence_path = self.freeze_fixture(temp_dir)
                    reviews = [
                        self.review(
                            REVIEW_ONE, agent_id="reviewer-1", findings=[], recommendation=first
                        ),
                        self.review(
                            REVIEW_TWO, agent_id="reviewer-2", findings=[], recommendation=second
                        ),
                    ]

                    result = self.evaluate(temp_dir, evidence_path, reviews)

                    self.assertEqual(result.agreement_class, MATERIAL_DISAGREEMENT)
                    self.assertIn(REASON_RECOMMENDATION_CONFLICT, result.reason_codes)

    def test_every_unanimous_recommendation_value_avoids_conflict(self) -> None:
        for value in ("accept", "reject", "inconclusive", "escalate"):
            with self.subTest(recommendation=value):
                with tempfile.TemporaryDirectory() as temp_dir:
                    evidence_path = self.freeze_fixture(temp_dir)
                    reviews = [
                        self.review(
                            REVIEW_ONE, agent_id="reviewer-1", findings=[], recommendation=value
                        ),
                        self.review(
                            REVIEW_TWO, agent_id="reviewer-2", findings=[], recommendation=value
                        ),
                    ]

                    result = self.evaluate(temp_dir, evidence_path, reviews)

                    self.assertEqual(result.agreement_class, UNANIMOUS_CLEAN)
                    self.assertFalse(result.recommendation_conflict)

    # ------------------------------------------------------------------
    # 12.3 finding disagreement
    # ------------------------------------------------------------------

    def test_one_clean_one_finding_bearing_is_material_disagreement(self) -> None:
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

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, MATERIAL_DISAGREEMENT)
            self.assertIn(REASON_FINDING_COVERAGE_CONFLICT, result.reason_codes)
            agreement = result.finding_agreements[0]
            self.assertEqual(agreement.reporting_review_ids, (REVIEW_ONE,))
            self.assertEqual(agreement.silent_review_ids, (REVIEW_TWO,))
            self.assertFalse(agreement.unanimous)

    def test_different_finding_sets_are_material_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[
                        self.finding(
                            "F-002",
                            summary="Missing docstring on the helper.",
                            evidence_refs=[artifact_b],
                        )
                    ],
                ),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, MATERIAL_DISAGREEMENT)
            self.assertIn(REASON_FINDING_COVERAGE_CONFLICT, result.reason_codes)
            self.assertEqual(len(result.finding_agreements), 2)
            self.assertTrue(all(not a.unanimous for a in result.finding_agreements))

    def test_different_severity_is_material_disagreement(self) -> None:
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
                    findings=[self.finding("F-002", severity="low", evidence_refs=[artifact_a])],
                ),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, MATERIAL_DISAGREEMENT)
            self.assertIn(REASON_FINDING_COVERAGE_CONFLICT, result.reason_codes)
            self.assertEqual(
                sorted(a.severity for a in result.finding_agreements), ["high", "low"]
            )

    def test_different_evidence_target_is_material_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-002", evidence_refs=[artifact_b])],
                ),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, MATERIAL_DISAGREEMENT)
            self.assertIn(REASON_FINDING_COVERAGE_CONFLICT, result.reason_codes)

    def test_partial_overlap_is_material_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            shared = self.finding("SHARED", evidence_refs=[artifact_a])
            extra = self.finding(
                "EXTRA",
                severity="medium",
                summary="Silent exception swallow.",
                evidence_refs=[artifact_b],
            )
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[dict(shared), extra]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[dict(shared)]),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, MATERIAL_DISAGREEMENT)
            self.assertIn(REASON_FINDING_COVERAGE_CONFLICT, result.reason_codes)
            unanimous = [a for a in result.finding_agreements if a.unanimous]
            contested = [a for a in result.finding_agreements if not a.unanimous]
            self.assertEqual(len(unanimous), 1)
            self.assertEqual(len(contested), 1)
            self.assertEqual(contested[0].silent_review_ids, (REVIEW_TWO,))

    # ------------------------------------------------------------------
    # 12.4 structural failure
    # ------------------------------------------------------------------

    def test_missing_required_review_is_deterministic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews, expected_review_count=3)

            self.assertEqual(result.agreement_class, DETERMINISTIC_FAILURE)
            self.assertIn(REASON_MISSING_REQUIRED_REVIEW, result.reason_codes)
            self.assertEqual(result.expected_review_count, 3)

    def test_quorum_is_not_assumed_when_not_supplied(self) -> None:
        """Omitting expected_review_count must not silently imply ADR-0003's three."""
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, UNANIMOUS_CLEAN)
            self.assertIsNone(result.expected_review_count)
            self.assertNotIn(REASON_MISSING_REQUIRED_REVIEW, result.reason_codes)

    def test_duplicate_review_id_is_deterministic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_ONE, agent_id="reviewer-2", findings=[]),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, DETERMINISTIC_FAILURE)
            self.assertIn(REASON_DUPLICATE_REVIEW_ID, result.reason_codes)

    def test_duplicate_reviewer_identity_is_deterministic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-1", findings=[]),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertEqual(result.agreement_class, DETERMINISTIC_FAILURE)
            self.assertIn(REASON_DUPLICATE_REVIEWER_IDENTITY, result.reason_codes)

    def test_task_mismatch_between_set_and_reviews_is_deterministic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            clean = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            finding_set = self.normalizer(temp_dir).normalize([clean], evidence_path=evidence_path)
            mutated = dataclasses.replace(finding_set, task_id=OTHER_TASK_ID)

            result = self.evaluator(temp_dir).evaluate(
                mutated, [clean], evidence_path=evidence_path
            )

            self.assertEqual(result.agreement_class, DETERMINISTIC_FAILURE)
            self.assertIn(REASON_TASK_ID_MISMATCH, result.reason_codes)

    def test_evidence_package_mismatch_is_deterministic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            clean = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            finding_set = self.normalizer(temp_dir).normalize([clean], evidence_path=evidence_path)
            mutated = dataclasses.replace(finding_set, evidence_package_id="other-package")

            result = self.evaluator(temp_dir).evaluate(
                mutated, [clean], evidence_path=evidence_path
            )

            self.assertEqual(result.agreement_class, DETERMINISTIC_FAILURE)
            self.assertIn(REASON_EVIDENCE_PACKAGE_MISMATCH, result.reason_codes)

    def test_unknown_review_id_in_set_is_deterministic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            first = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            second = self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[])
            finding_set = self.normalizer(temp_dir).normalize(
                [first, second], evidence_path=evidence_path
            )

            # Evaluate against only one of the two reviews the set was built from.
            result = self.evaluator(temp_dir).evaluate(
                finding_set, [first], evidence_path=evidence_path
            )

            self.assertEqual(result.agreement_class, DETERMINISTIC_FAILURE)
            self.assertIn(REASON_REVIEW_ID_MISMATCH, result.reason_codes)

    def test_tampered_finding_set_hash_is_deterministic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            clean = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            finding_set = self.normalizer(temp_dir).normalize([clean], evidence_path=evidence_path)
            tampered = dataclasses.replace(finding_set, finding_set_sha256="deadbeef")

            result = self.evaluator(temp_dir).evaluate(
                tampered, [clean], evidence_path=evidence_path
            )

            self.assertEqual(result.agreement_class, DETERMINISTIC_FAILURE)
            self.assertIn(REASON_FINDING_SET_HASH_MISMATCH, result.reason_codes)

    def test_prohibited_authority_claim_is_deterministic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            clean = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            finding_set = self.normalizer(temp_dir).normalize([clean], evidence_path=evidence_path)
            escalated = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            escalated["authority"]["can_authorize_execution"] = True

            result = self.evaluator(temp_dir).evaluate(
                finding_set, [escalated], evidence_path=evidence_path
            )

            self.assertEqual(result.agreement_class, DETERMINISTIC_FAILURE)
            self.assertIn(REASON_INVALID_REVIEW_REPORT, result.reason_codes)

    def test_invalid_normalized_set_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            clean = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])

            with self.assertRaises(ConsensusEvaluationError):
                self.evaluator(temp_dir).evaluate(
                    {"not": "a finding set"},  # type: ignore[arg-type]
                    [clean],
                    evidence_path=evidence_path,
                )

    def test_no_reviews_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            clean = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            finding_set = self.normalizer(temp_dir).normalize([clean], evidence_path=evidence_path)

            with self.assertRaises(ConsensusEvaluationError):
                self.evaluator(temp_dir).evaluate(finding_set, [], evidence_path=evidence_path)

    def test_malformed_review_json_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            clean = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            finding_set = self.normalizer(temp_dir).normalize([clean], evidence_path=evidence_path)
            bad_path = Path(temp_dir) / "bad_review.json"
            bad_path.write_text("{not json", encoding="utf-8")

            with self.assertRaises(ConsensusEvaluationError):
                self.evaluator(temp_dir).evaluate(
                    finding_set, [bad_path], evidence_path=evidence_path
                )

    def test_invalid_expected_review_count_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            clean = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])
            finding_set = self.normalizer(temp_dir).normalize([clean], evidence_path=evidence_path)

            with self.assertRaises(ConsensusEvaluationError):
                self.evaluator(temp_dir).evaluate(
                    finding_set,
                    [clean],
                    evidence_path=evidence_path,
                    expected_review_count=0,
                )

    # ------------------------------------------------------------------
    # 12.5 authority and side effects
    # ------------------------------------------------------------------

    def test_evaluation_writes_nothing_and_grants_no_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                )
            ]
            finding_set = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)
            base_dir = Path(temp_dir)
            before = {
                path.relative_to(base_dir).as_posix(): path.stat().st_mtime_ns
                for path in sorted(base_dir.rglob("*"))
                if path.is_file()
            }

            result = self.evaluator(temp_dir).evaluate(
                finding_set, reviews, evidence_path=evidence_path
            )

            after = {
                path.relative_to(base_dir).as_posix(): path.stat().st_mtime_ns
                for path in sorted(base_dir.rglob("*"))
                if path.is_file()
            }
            self.assertEqual(before, after)

            document = result.as_document()
            for forbidden in (
                "authority",
                "acceptance",
                "disposition",
                "state",
                "can_execute",
                "can_authorize_execution",
                "rationale",
            ):
                self.assertNotIn(forbidden, document)

    def test_agreement_class_is_never_a_terminal_disposition(self) -> None:
        """6B must not emit 6C's ACCEPTED/ESCALATED/BLOCKED/INCONCLUSIVE vocabulary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            self.assertIn(
                result.agreement_class,
                (UNANIMOUS_CLEAN, UNANIMOUS_FINDING, MATERIAL_DISAGREEMENT, DETERMINISTIC_FAILURE),
            )
            self.assertNotIn(
                result.agreement_class,
                ("ACCEPTED", "REJECTED", "ESCALATED", "BLOCKED", "INCONCLUSIVE"),
            )

    # ------------------------------------------------------------------
    # 12.6 immutability
    # ------------------------------------------------------------------

    def test_result_is_frozen_and_uses_tuples(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                )
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            with self.assertRaises(dataclasses.FrozenInstanceError):
                result.agreement_class = MATERIAL_DISAGREEMENT  # type: ignore[misc]
            with self.assertRaises(dataclasses.FrozenInstanceError):
                result.finding_agreements[0].unanimous = False  # type: ignore[misc]
            self.assertIsInstance(result.review_ids, tuple)
            self.assertIsInstance(result.reviewer_agent_ids, tuple)
            self.assertIsInstance(result.finding_agreements, tuple)
            self.assertIsInstance(result.recommendations, tuple)
            self.assertIsInstance(result.reason_codes, tuple)
            self.assertIsInstance(result.finding_agreements[0].reporting_review_ids, tuple)

    # ------------------------------------------------------------------
    # 12.7 hash regression
    # ------------------------------------------------------------------

    def test_evaluation_hash_is_pinned(self) -> None:
        """Pinned so a silent change to the hashed shape fails loudly.

        6D binds acceptance to this hash and 6E must reject tampered consensus,
        so the hashed document shape is a contract, not an implementation detail.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-777", evidence_refs=[artifact_a])],
                ),
            ]

            result = self.evaluate(temp_dir, evidence_path, reviews, expected_review_count=2)

            self.assertEqual(result.agreement_class, UNANIMOUS_FINDING)
            self.assertEqual(
                result.evaluation_sha256,
                "ee9799411f1fa8fce747372de83b42b1588f8e9371b48118a85ab4453851a386",
            )

    def test_hash_excludes_itself_and_covers_the_public_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            reviews = [self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[])]

            result = self.evaluate(temp_dir, evidence_path, reviews)

            document = result.as_document()
            self.assertIn("evaluation_sha256", document)
            self.assertEqual(document["evaluation_sha256"], result.evaluation_sha256)
            # every other public field participates in the hashed shape
            hashed_keys = set(document) - {"evaluation_sha256"}
            self.assertEqual(
                hashed_keys,
                {
                    "task_id",
                    "evidence_package_id",
                    "finding_set_sha256",
                    "agreement_class",
                    "review_ids",
                    "reviewer_agent_ids",
                    "expected_review_count",
                    "finding_agreements",
                    "recommendations",
                    "recommendation_conflict",
                    "reason_codes",
                },
            )

    def test_agreement_class_change_changes_the_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            agreeing = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[self.finding("F-777", evidence_refs=[artifact_a])],
                ),
            ]
            disagreeing = [
                agreeing[0],
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[]),
            ]

            first = self.evaluate(temp_dir, evidence_path, agreeing)
            second = self.evaluate(temp_dir, evidence_path, disagreeing)

            self.assertNotEqual(first.agreement_class, second.agreement_class)
            self.assertNotEqual(first.evaluation_sha256, second.evaluation_sha256)


if __name__ == "__main__":
    unittest.main()
