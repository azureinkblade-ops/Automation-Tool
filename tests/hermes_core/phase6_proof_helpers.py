"""Shared helpers for the Hermes Phase 6F end-to-end deterministic proof.

These helpers drive the PRODUCTION API path from frozen evidence through
persisted ACCEPTED governance state. They do not reimplement any consensus,
disposition, acceptance, or persistence rule — they call the real constructors
and validators and bind their outputs together.

Path exercised:

    EvidencePackageBuilder.freeze_to_file
        -> ReviewReportValidator.validate            (validated review input)
        -> ReviewerRegistry.from_documents
        -> ReviewAssignmentBuilder.build             (eligibility + assignment)
        -> ReviewSessionBuilder.build                (read-only session)
        -> ReviewRunnerStub.prepare                  (documented non-executing stub)
        -> ReviewOutcomeValidator.validate           (outcome record)
        -> FindingNormalizer.normalize               (6A)
        -> ConsensusEvaluator.evaluate               (6B)
        -> ConsensusDispositionEngine.dispose        (6C)
        -> AcceptanceArtifactBuilder.build           (6D)
        -> SQLiteGovernanceStore.record_*            (6E)

The review runner is intentionally a non-executing stub; model execution is
out of scope for Phase 6 (guardrail: no worker executed).
"""
from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.hermes_core import (
    AcceptanceArtifact,
    AcceptanceArtifactBuilder,
    ConsensusDisposition,
    ConsensusDispositionEngine,
    ConsensusEvaluation,
    FindingNormalizer,
    NormalizedFindingSet,
    ReviewAssignmentBuilder,
    ReviewOutcomeValidator,
    ReviewReportValidator,
    ReviewRunnerStub,
    ReviewSessionBuilder,
    SQLiteGovernanceStore,
    load_schema_catalog,
    sha256_payload,
)
from tools.hermes_core.consensus_evaluator import (
    ConsensusEvaluator,
    DETERMINISTIC_FAILURE,
    MATERIAL_DISAGREEMENT,
    UNANIMOUS_CLEAN,
    UNANIMOUS_FINDING,
)
from tools.hermes_core.consensus_disposition import (
    BLOCKING_SEVERITIES,
    DISPOSITION_ACCEPTED,
    DISPOSITION_BLOCKED,
    DISPOSITION_ESCALATED,
)
from tools.hermes_core.evidence import EvidencePackageBuilder
from tools.hermes_core.reviewer_registry import ReviewerAgent, ReviewerRegistry


# Fixed deterministic fixtures (plan section 5).
TASK_ID = "11111111-1111-1111-1111-111111111111"
EVIDENCE_PACKAGE_ID = "evidence-phase6f-fixture"
REVIEW_IDS = [
    "22222222-2222-2222-2222-222222222222",
    "33333333-3333-3333-3333-333333333333",
    "44444444-4444-4444-4444-444444444444",
]
REVIEWER_AGENT_IDS = ["reviewer-1", "reviewer-2", "reviewer-3"]
REVIEWER_MODEL_ID = "local-model"
EXPECTED_REVIEW_COUNT = 3
FREEZE_AT = "2026-08-11T10:00:00Z"
REVIEW_STARTED = "2026-08-11T10:05:00Z"
REVIEW_COMPLETED = "2026-08-11T10:06:00Z"
SESSION_AT = "2026-08-11T10:10:00Z"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def reviewer_doc(agent_id: str) -> dict[str, Any]:
    """A schema-valid hermes.agent document with no execution authority."""
    return {
        "agent_id": agent_id,
        "display_name": f"Reviewer {agent_id}",
        "model_id": REVIEWER_MODEL_ID,
        "status": "active",
        "role": "reviewer",
        "allowed_tools": [],
        "denied_tools": [],
        "authority": {
            "can_review": True,
            "can_modify_governance_state": False,
            "can_authorize_execution": False,
            "can_execute": False,
        },
        "document": {},
    }


def build_registry(catalog: Any) -> ReviewerRegistry:
    agents = [ReviewerAgent(**_agent_fields(catalog, reviewer_doc(a))) for a in REVIEWER_AGENT_IDS]
    return ReviewerRegistry(catalog, agents)


def _agent_fields(catalog: Any, doc: dict[str, Any]) -> dict[str, Any]:
    """Construct ReviewerAgent kwargs from a validated document."""
    from tools.hermes_core.reviewer_registry import _reviewer_from_document

    return _reviewer_from_document(doc).__dict__


def freeze_evidence(temp_dir: Path) -> Path:
    catalog = load_schema_catalog(project_root())
    base = Path(temp_dir)
    (base / "artifact_a.txt").write_text("evidence a", encoding="utf-8")
    (base / "artifact_b.txt").write_text("evidence b", encoding="utf-8")
    builder = EvidencePackageBuilder(catalog, base_dir=base)
    builder.freeze_to_file(
        base / "evidence.json",
        task_id=TASK_ID,
        artifacts=["artifact_a.txt", "artifact_b.txt"],
        evidence_package_id=EVIDENCE_PACKAGE_ID,
        created_at=FREEZE_AT,
    )
    return base / "evidence.json"


def freeze_evidence_ids(temp_dir: Path) -> tuple[Path, list[str]]:
    """Freeze evidence and return (path, real artifact IDs from the inventory)."""
    path = freeze_evidence(temp_dir)
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [item["artifact_id"] for item in doc["inventory"]]
    return path, ids


def raw_review(review_id: str, agent_id: str, *, findings: list[dict], recommendation: str) -> dict[str, Any]:
    return {
        "review_id": review_id,
        "task_id": TASK_ID,
        "evidence_package_id": EVIDENCE_PACKAGE_ID,
        "reviewer": {
            "agent_id": agent_id,
            "model_id": REVIEWER_MODEL_ID,
            "role": "architect_reviewer",
        },
        "started_at": REVIEW_STARTED,
        "completed_at": REVIEW_COMPLETED,
        "findings": findings,
        "recommendation": recommendation,
        "authority": {
            "can_modify_state": False,
            "can_authorize_execution": False,
            "can_execute": False,
        },
    }


def raw_finding(
    finding_id: str,
    *,
    severity: str = "medium",
    summary: str = "Sample finding for the Phase 6F deterministic proof.",
    evidence_refs: list[str] | None = None,
    confidence: float = 0.7,
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "summary": summary,
        "evidence_refs": evidence_refs or [],
        "confidence": confidence,
    }


def validate_reports(evidence_path: Path, reviews: list[dict]) -> list[dict]:
    """Validate every review against the frozen evidence; return the valid reports."""
    catalog = load_schema_catalog(project_root())
    validator = ReviewReportValidator(catalog, base_dir=evidence_path.parent)
    valid: list[dict] = []
    for review in reviews:
        result = validator.validate(review, evidence_path=evidence_path)
        if not result.valid:
            raise AssertionError(f"Review {review['review_id']} failed validation: {result.issues}")
        valid.append(review)
    return valid


def assign_and_session(evidence_path: Path, reviews: list[dict]) -> dict[str, Any]:
    """Run eligibility, assignment, session, runner-stub, outcome validation.

    Returns a context dict with the validated reports and outcome. The runner is
    the documented non-executing stub (no model is invoked).
    """
    catalog = load_schema_catalog(project_root())
    base = evidence_path.parent
    registry = build_registry(catalog)
    assignment = ReviewAssignmentBuilder(catalog, base_dir=base).build(
        current_state="READY_FOR_REVIEW",
        evidence_path=evidence_path,
        parent_ref="phase6f-parent-event-1",
        registry=registry,
        minimum_reviewers=EXPECTED_REVIEW_COUNT,
    )
    if not assignment.ready:
        raise AssertionError(f"Review assignment not ready: {assignment.reasons}")
    session = ReviewSessionBuilder().build(
        plan=assignment, evidence_path=evidence_path, created_at=SESSION_AT
    )
    runner_result = ReviewRunnerStub().prepare(session)
    if runner_result.status != ReviewRunnerStub.pending_status:
        raise AssertionError(f"Unexpected runner status: {runner_result.status}")
    outcome = ReviewOutcomeValidator(catalog, base_dir=base).validate(
        {
            "review_outcome_id": "phase6f-outcome-1",
            "task_id": TASK_ID,
            "evidence_package_id": EVIDENCE_PACKAGE_ID,
            "status": "accepted",
            "recorded_at": "2026-08-11T10:15:00Z",
            "review_ids": [r["review_id"] for r in reviews],
            "decision": "accept",
            "authority": {
                "can_modify_state": False,
                "can_authorize_execution": False,
                "can_execute": False,
            },
        },
        evidence_path=evidence_path,
        reviews=reviews,
    )
    if not outcome.valid:
        raise AssertionError(f"Review outcome invalid: {outcome.issues}")
    return {
        "assignment": assignment,
        "session": session,
        "runner_result": runner_result,
        "outcome": outcome,
    }


def build_consensus_artifacts(
    temp_dir: Path,
    reviews: list[dict],
    *,
    expected_review_count: int = EXPECTED_REVIEW_COUNT,
) -> dict[str, Any]:
    """Drive 6A -> 6B -> 6C over validated reviews (stops before acceptance)."""
    catalog = load_schema_catalog(project_root())
    base = Path(temp_dir)
    evidence_path = freeze_evidence(base)
    valid = validate_reports(evidence_path, reviews)
    assign_and_session(evidence_path, valid)

    fs: NormalizedFindingSet = FindingNormalizer(catalog, base_dir=base).normalize(
        valid, evidence_path=evidence_path
    )
    ev: ConsensusEvaluation = ConsensusEvaluator(catalog, base_dir=base).evaluate(
        fs, valid, evidence_path=evidence_path, expected_review_count=expected_review_count
    )
    disp: ConsensusDisposition = ConsensusDispositionEngine(catalog, base_dir=base).dispose(
        ev, fs, expected_review_count=expected_review_count
    )
    return {
        "evidence_path": evidence_path,
        "evidence_doc": json.loads(evidence_path.read_text(encoding="utf-8")),
        "reviews": valid,
        "finding_set": fs,
        "evaluation": ev,
        "disposition": disp,
    }


def build_accepted_artifacts(
    temp_dir: Path,
    reviews: list[dict],
    *,
    expected_review_count: int = EXPECTED_REVIEW_COUNT,
) -> dict[str, Any]:
    """Drive 6A -> 6B -> 6C -> 6D over validated reviews. Returns the artifacts dict."""
    arts = build_consensus_artifacts(temp_dir, reviews, expected_review_count=expected_review_count)
    acc: AcceptanceArtifact = AcceptanceArtifactBuilder(
        load_schema_catalog(project_root()), base_dir=Path(temp_dir)
    ).build(arts["disposition"], arts["evaluation"], arts["finding_set"])
    arts["acceptance"] = acc
    return arts


def persist_accepted_chain(store: SQLiteGovernanceStore, arts: dict[str, Any]) -> None:
    """Persist the full 6A->6D chain plus evidence + reviews into the store."""
    store.record_evidence_record(arts["evidence_doc"])
    store.record_review_documents(arts["reviews"])
    store.record_finding_set(arts["finding_set"])
    store.record_consensus_evaluation(arts["evaluation"])
    store.record_consensus_disposition(arts["disposition"])
    store.record_acceptance(arts["acceptance"])


def advance_to_accepted(store: SQLiteGovernanceStore, arts: dict[str, Any]) -> None:
    store.record_transition(TASK_ID, "UNDER_REVIEW", "CONSENSUS_CALCULATED")
    store.record_transition(TASK_ID, "CONSENSUS_CALCULATED", "ACCEPTED")
