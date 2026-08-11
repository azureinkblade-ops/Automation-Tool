from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import (
    EvidencePackageBuilder,
    FindingNormalizationError,
    FindingNormalizer,
    load_schema_catalog,
)


TASK_ID = "11111111-1111-1111-1111-111111111111"
REVIEW_ONE = "22222222-2222-2222-2222-222222222222"
REVIEW_TWO = "33333333-3333-3333-3333-333333333333"
REVIEW_THREE = "44444444-4444-4444-4444-444444444444"
EVIDENCE_PACKAGE_ID = "evidence-normalizer-fixture"


class HermesFindingNormalizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

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
        recommendation: str = "reject",
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

    # ------------------------------------------------------------------
    # positive
    # ------------------------------------------------------------------

    def test_single_report_single_finding_normalizes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            review = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=[artifact_a])],
            )

            result = self.normalizer(temp_dir).normalize([review], evidence_path=evidence_path)

            self.assertEqual(result.task_id, TASK_ID)
            self.assertEqual(result.evidence_package_id, EVIDENCE_PACKAGE_ID)
            self.assertEqual(result.finding_count, 1)
            self.assertEqual(result.review_ids, (REVIEW_ONE,))
            self.assertTrue(result.findings[0].finding_key.startswith("finding-"))

    def test_multiple_reports_normalize(self) -> None:
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
                            "F-100",
                            severity="low",
                            summary="Missing docstring on the helper.",
                            evidence_refs=[artifact_b],
                        )
                    ],
                ),
            ]

            result = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)

            self.assertEqual(result.finding_count, 2)
            self.assertEqual(result.review_ids, (REVIEW_ONE, REVIEW_TWO))
            # severity ordering: high before low
            self.assertEqual(
                [finding.severity for finding in result.findings],
                ["high", "low"],
            )

    def test_equivalent_duplicate_findings_collapse(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            reviews = [
                self.review(
                    REVIEW_ONE,
                    agent_id="reviewer-1",
                    findings=[self.finding("F-001", evidence_refs=[artifact_a])],
                ),
                # Same severity, same evidence target, same summary with different
                # whitespace and casing, different reviewer-local finding id.
                self.review(
                    REVIEW_TWO,
                    agent_id="reviewer-2",
                    findings=[
                        self.finding(
                            "OTHER-ID-9",
                            summary="unbounded   retry loop in the WORKER path.",
                            evidence_refs=[artifact_a],
                            confidence=0.4,
                        )
                    ],
                ),
            ]

            result = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)

            self.assertEqual(result.finding_count, 1)
            finding = result.findings[0]
            self.assertEqual(len(finding.sources), 2)
            self.assertEqual(finding.review_ids, (REVIEW_ONE, REVIEW_TWO))
            self.assertEqual(finding.reviewer_agent_ids, ("reviewer-1", "reviewer-2"))

    def test_source_references_are_preserved(self) -> None:
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
                    role="security_reviewer",
                    findings=[self.finding("F-777", evidence_refs=[artifact_a])],
                    recommendation="escalate",
                ),
            ]

            result = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)

            finding = result.findings[0]
            sources = {source.review_id: source for source in finding.sources}
            self.assertEqual(sources[REVIEW_ONE].finding_id, "F-001")
            self.assertEqual(sources[REVIEW_ONE].reviewer_role, "architect_reviewer")
            self.assertEqual(sources[REVIEW_ONE].recommendation, "reject")
            self.assertEqual(sources[REVIEW_TWO].finding_id, "F-777")
            self.assertEqual(sources[REVIEW_TWO].reviewer_role, "security_reviewer")
            self.assertEqual(sources[REVIEW_TWO].recommendation, "escalate")
            self.assertEqual(sources[REVIEW_TWO].reviewer_model_id, "local-model")
            # Both recommendations survive for the later 6B evaluator.
            self.assertEqual(finding.recommendations, ("escalate", "reject"))

    def test_evidence_references_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            review = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=[artifact_b, artifact_a])],
            )

            result = self.normalizer(temp_dir).normalize([review], evidence_path=evidence_path)

            self.assertEqual(
                result.findings[0].evidence_refs,
                tuple(sorted([artifact_a, artifact_b])),
            )

    # ------------------------------------------------------------------
    # determinism
    # ------------------------------------------------------------------

    def test_report_order_does_not_change_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            first = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=[artifact_a])],
            )
            second = self.review(
                REVIEW_TWO,
                agent_id="reviewer-2",
                findings=[
                    self.finding(
                        "F-002",
                        severity="medium",
                        summary="Silent exception swallow.",
                        evidence_refs=[artifact_b],
                    )
                ],
            )
            normalizer = self.normalizer(temp_dir)

            forward = normalizer.normalize([first, second], evidence_path=evidence_path)
            reverse = normalizer.normalize([second, first], evidence_path=evidence_path)

            self.assertEqual(forward.as_document(), reverse.as_document())
            self.assertEqual(forward.finding_set_sha256, reverse.finding_set_sha256)

    def test_finding_order_within_a_report_does_not_change_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, artifact_b = self.artifact_ids(evidence_path)
            finding_one = self.finding("F-001", evidence_refs=[artifact_a])
            finding_two = self.finding(
                "F-002",
                severity="critical",
                summary="Credential written to disk.",
                evidence_refs=[artifact_b],
            )
            normalizer = self.normalizer(temp_dir)

            forward = normalizer.normalize(
                [self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[finding_one, finding_two])],
                evidence_path=evidence_path,
            )
            reverse = normalizer.normalize(
                [self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[finding_two, finding_one])],
                evidence_path=evidence_path,
            )

            self.assertEqual(forward.as_document(), reverse.as_document())
            self.assertEqual(forward.finding_set_sha256, reverse.finding_set_sha256)

    def test_reviewer_order_does_not_change_finding_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            shared = self.finding("F-001", evidence_refs=[artifact_a])
            reviews = [
                self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[dict(shared)]),
                self.review(REVIEW_TWO, agent_id="reviewer-2", findings=[dict(shared)]),
                self.review(REVIEW_THREE, agent_id="reviewer-3", findings=[dict(shared)]),
            ]
            normalizer = self.normalizer(temp_dir)

            forward = normalizer.normalize(reviews, evidence_path=evidence_path)
            shuffled = normalizer.normalize(list(reversed(reviews)), evidence_path=evidence_path)

            self.assertEqual(forward.findings[0].finding_key, shuffled.findings[0].finding_key)
            self.assertEqual(forward.as_document(), shuffled.as_document())

    def test_repeat_execution_is_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            review = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=[artifact_a])],
            )
            normalizer = self.normalizer(temp_dir)

            first = normalizer.normalize([review], evidence_path=evidence_path)
            second = normalizer.normalize([review], evidence_path=evidence_path)

            self.assertEqual(first.finding_set_sha256, second.finding_set_sha256)
            self.assertEqual(first.as_document(), second.as_document())

    def test_coalesced_summary_variant_does_not_depend_on_report_order(self) -> None:
        """Regression: the representative summary and set hash must not follow input order.

        Two reviewers wording the same finding with different casing and spacing
        coalesce to one finding. Before this was fixed the display summary was
        first-seen, so the normalized document and finding_set_sha256 flipped when
        the reports were supplied in the opposite order.
        """
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
                findings=[
                    self.finding(
                        "ZZZ",
                        summary="unbounded   retry loop in the WORKER path.",
                        evidence_refs=[artifact_a],
                    )
                ],
            )
            normalizer = self.normalizer(temp_dir)

            forward = normalizer.normalize([first, second], evidence_path=evidence_path)
            reverse = normalizer.normalize([second, first], evidence_path=evidence_path)

            self.assertEqual(forward.finding_count, 1)
            self.assertEqual(forward.findings[0].summary, reverse.findings[0].summary)
            self.assertEqual(forward.finding_set_sha256, reverse.finding_set_sha256)
            self.assertEqual(forward.as_document(), reverse.as_document())

    # ------------------------------------------------------------------
    # separation of materially different findings
    # ------------------------------------------------------------------

    def test_different_severity_remains_distinct(self) -> None:
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

            result = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)

            self.assertEqual(result.finding_count, 2)
            self.assertEqual(
                len({finding.finding_key for finding in result.findings}),
                2,
            )

    def test_different_evidence_target_remains_distinct(self) -> None:
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

            result = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)

            self.assertEqual(result.finding_count, 2)

    def test_different_summary_remains_distinct(self) -> None:
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
                    findings=[
                        self.finding(
                            "F-002",
                            summary="Completely different problem entirely.",
                            evidence_refs=[artifact_a],
                        )
                    ],
                ),
            ]

            result = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)

            self.assertEqual(result.finding_count, 2)

    def test_differing_recommendation_does_not_split_the_same_finding(self) -> None:
        """recommendation is review-level, so it is preserved per source, not identifying.

        Coalescing here is deliberate: it is the input 6B needs to detect
        material disagreement on an otherwise identical finding.
        """
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
                    recommendation="accept",
                ),
            ]

            result = self.normalizer(temp_dir).normalize(reviews, evidence_path=evidence_path)

            self.assertEqual(result.finding_count, 1)
            self.assertEqual(result.findings[0].recommendations, ("accept", "reject"))

    # ------------------------------------------------------------------
    # rejection
    # ------------------------------------------------------------------

    def test_no_reports_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)

            with self.assertRaises(FindingNormalizationError):
                self.normalizer(temp_dir).normalize([], evidence_path=evidence_path)

    def test_malformed_report_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            bad_path = Path(temp_dir) / "bad_review.json"
            bad_path.write_text("{not json", encoding="utf-8")

            with self.assertRaises(FindingNormalizationError):
                self.normalizer(temp_dir).normalize([bad_path], evidence_path=evidence_path)

    def test_report_failing_validation_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            review = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=[artifact_a])],
            )
            del review["recommendation"]

            with self.assertRaises(FindingNormalizationError):
                self.normalizer(temp_dir).normalize([review], evidence_path=evidence_path)

    def test_missing_required_finding_field_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            finding = self.finding("F-001", evidence_refs=[artifact_a])
            del finding["severity"]
            review = self.review(REVIEW_ONE, agent_id="reviewer-1", findings=[finding])

            with self.assertRaises(FindingNormalizationError):
                self.normalizer(temp_dir).normalize([review], evidence_path=evidence_path)

    def test_unknown_evidence_reference_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            review = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=["artifact-does-not-exist"])],
            )

            with self.assertRaises(FindingNormalizationError):
                self.normalizer(temp_dir).normalize([review], evidence_path=evidence_path)

    def test_reports_bound_to_different_tasks_rejected(self) -> None:
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
            second["task_id"] = "55555555-5555-5555-5555-555555555555"

            with self.assertRaises(FindingNormalizationError):
                self.normalizer(temp_dir).normalize([first, second], evidence_path=evidence_path)

    def test_report_claiming_authority_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            review = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=[artifact_a])],
            )
            review["authority"]["can_authorize_execution"] = True

            with self.assertRaises(FindingNormalizationError):
                self.normalizer(temp_dir).normalize([review], evidence_path=evidence_path)

    # ------------------------------------------------------------------
    # authority and side effects
    # ------------------------------------------------------------------

    def test_normalization_writes_no_files_and_grants_no_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            review = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=[artifact_a])],
            )
            base_dir = Path(temp_dir)
            before = {
                path.relative_to(base_dir).as_posix(): path.stat().st_mtime_ns
                for path in sorted(base_dir.rglob("*"))
                if path.is_file()
            }

            result = self.normalizer(temp_dir).normalize([review], evidence_path=evidence_path)

            after = {
                path.relative_to(base_dir).as_posix(): path.stat().st_mtime_ns
                for path in sorted(base_dir.rglob("*"))
                if path.is_file()
            }
            # No new files, no ledger, no acceptance artifact, no rewrites.
            self.assertEqual(before, after)

            document = result.as_document()
            for forbidden in ("authority", "consensus", "acceptance", "disposition", "state"):
                self.assertNotIn(forbidden, document)

    def test_normalized_set_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = self.freeze_fixture(temp_dir)
            artifact_a, _ = self.artifact_ids(evidence_path)
            review = self.review(
                REVIEW_ONE,
                agent_id="reviewer-1",
                findings=[self.finding("F-001", evidence_refs=[artifact_a])],
            )

            result = self.normalizer(temp_dir).normalize([review], evidence_path=evidence_path)

            with self.assertRaises(dataclasses.FrozenInstanceError):
                result.findings[0].severity = "low"  # type: ignore[misc]
            with self.assertRaises(dataclasses.FrozenInstanceError):
                result.task_id = "mutated"  # type: ignore[misc]
            self.assertIsInstance(result.findings, tuple)
            self.assertIsInstance(result.findings[0].sources, tuple)


if __name__ == "__main__":
    unittest.main()
