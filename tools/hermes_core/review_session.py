"""Build and verify read-only Hermes review session envelopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import canonical_json, sha256_payload
from .review_assignment import ReviewAssignmentPlan


class ReviewSessionError(ValueError):
    """Raised when a review session envelope is invalid."""


@dataclass(frozen=True)
class ReviewSessionEnvelope:
    document: dict[str, Any]
    path: Path | None = None

    @property
    def review_session_id(self) -> str:
        return str(self.document["review_session_id"])

    @property
    def session_sha256(self) -> str:
        return str(self.document["session_sha256"])


class ReviewSessionBuilder:
    """Freeze reviewer assignments into a read-only session envelope."""

    def build(
        self,
        *,
        plan: ReviewAssignmentPlan,
        evidence_path: Path | str,
        review_session_id: str | None = None,
        created_at: str | None = None,
    ) -> ReviewSessionEnvelope:
        if not plan.ready:
            raise ReviewSessionError("Review assignment plan is not ready")
        if not plan.assignments:
            raise ReviewSessionError("Review session requires at least one assignment")
        if not plan.task_id:
            raise ReviewSessionError("Review session requires task_id")
        if not plan.evidence_package_id:
            raise ReviewSessionError("Review session requires evidence_package_id")

        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        assignments = [
            {
                "agent_id": assignment.agent_id,
                "model_id": assignment.model_id,
                "review_role": assignment.review_role,
                "evidence_package_id": assignment.evidence_package_id,
            }
            for assignment in plan.assignments
        ]
        session_id = review_session_id or _default_session_id(
            plan.task_id,
            plan.evidence_package_id,
            assignments,
        )
        without_hash = {
            "review_session_id": session_id,
            "task_id": plan.task_id,
            "evidence_package_id": plan.evidence_package_id,
            "evidence_path": str(evidence_path),
            "created_at": timestamp,
            "read_only": True,
            "assignments": assignments,
        }
        document = {
            **without_hash,
            "session_sha256": sha256_payload(without_hash),
        }
        self._validate_document(document)
        return ReviewSessionEnvelope(document=document)

    def freeze_to_file(
        self,
        output_path: Path | str,
        *,
        plan: ReviewAssignmentPlan,
        evidence_path: Path | str,
        review_session_id: str | None = None,
        created_at: str | None = None,
    ) -> ReviewSessionEnvelope:
        envelope = self.build(
            plan=plan,
            evidence_path=evidence_path,
            review_session_id=review_session_id,
            created_at=created_at,
        )
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(envelope.document) + "\n", encoding="utf-8")
        return ReviewSessionEnvelope(document=envelope.document, path=target)

    def load(self, envelope_path: Path | str) -> ReviewSessionEnvelope:
        path = Path(envelope_path)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ReviewSessionError(f"Review session envelope is not valid JSON: {path}") from exc
        if not isinstance(document, dict):
            raise ReviewSessionError("Review session envelope must be a JSON object")
        return ReviewSessionEnvelope(document=document, path=path)

    def verify(self, envelope: ReviewSessionEnvelope | Path | str) -> bool:
        session = self.load(envelope) if not isinstance(envelope, ReviewSessionEnvelope) else envelope
        document = session.document
        self._validate_document(document)
        expected_without_hash = {
            key: value
            for key, value in document.items()
            if key != "session_sha256"
        }
        if document["session_sha256"] != sha256_payload(expected_without_hash):
            raise ReviewSessionError("Review session envelope hash mismatch")
        return True

    def _validate_document(self, document: dict[str, Any]) -> None:
        required = (
            "review_session_id",
            "task_id",
            "evidence_package_id",
            "evidence_path",
            "created_at",
            "read_only",
            "assignments",
            "session_sha256",
        )
        for key in required:
            if key not in document:
                raise ReviewSessionError(f"Review session envelope missing {key}")
        if document["read_only"] is not True:
            raise ReviewSessionError("Review session envelope must be read-only")
        if not isinstance(document["assignments"], list) or not document["assignments"]:
            raise ReviewSessionError("Review session envelope requires assignments")
        for assignment in document["assignments"]:
            self._validate_assignment(assignment)

    def _validate_assignment(self, assignment: Any) -> None:
        if not isinstance(assignment, dict):
            raise ReviewSessionError("Review session assignment must be an object")
        for key in ("agent_id", "model_id", "review_role", "evidence_package_id"):
            if not isinstance(assignment.get(key), str) or not assignment.get(key):
                raise ReviewSessionError(f"Review session assignment missing {key}")


def _default_session_id(
    task_id: str,
    evidence_package_id: str,
    assignments: list[dict[str, str]],
) -> str:
    seed = {
        "task_id": task_id,
        "evidence_package_id": evidence_package_id,
        "assignments": assignments,
    }
    return f"review-session-{sha256_payload(seed)[:16]}"
