"""Build an immutable acceptance artifact from a verified Phase 6C disposition.

This is the fourth deterministic consensus primitive. It consumes a verified
``ConsensusDisposition`` (6C) together with the upstream ``ConsensusEvaluation``
(6B) and ``NormalizedFindingSet`` (6A) and, *only when the disposition is
acceptance-eligible*, binds them into one immutable acceptance record.

It is deterministic, evidence-bound, auditable, read-only with respect to
Hermes state, and non-authoritative with respect to execution. It performs no
persistence, mutates no task state, appends no ledger event, authorizes no
execution, invokes no model, adjudicates no reviewer, and introduces no
majority-vote rule. Those responsibilities belong to 6E or later.

The repository already owns the terminal disposition vocabulary and the
``hermes.acceptance`` schema; this module reuses them and does not invent
parallel names. The canonical acceptance id follows the ``acceptance-<16 hex>``
convention and is derived from the acceptance core hash (the canonical
acceptance document excluding ``acceptance_id``/``acceptance_sha256``/
``accepted_at``), which seeds the final ``acceptance_sha256``; not from runtime
state.

Eligibility is exactly the acceptance-eligible terminal disposition already
defined by ``consensus.schema.yaml`` and ADR-0003 / ADR-0004:

    ConsensusDisposition.disposition == ACCEPTED  -> acceptance may be built
    anything else (REJECTED/ESCALATED/BLOCKED/INCONCLUSIVE)
                                          -> acceptance must not be built

No acceptance rule is invented here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from .consensus_disposition import (
    DISPOSITION_ACCEPTED,
    ConsensusDisposition,
    _disposition_document,
)
from .consensus_evaluator import (
    ConsensusEvaluation,
    _evaluation_document,
)
from .finding_normalizer import (
    NormalizedFindingSet,
)
from .consensus_disposition import _finding_set_document
from .hashing import sha256_payload
from .schemas import SchemaCatalog


# Eligibility is the single canonical acceptance-eligible disposition from the
# consensus schema enum. Nothing else is invented.
ACCEPTANCE_ELIGIBLE_DISPOSITION = DISPOSITION_ACCEPTED

# Acceptance never authorizes execution (ADR-0004). The authority block matches
# the existing hermes.acceptance schema const constraints.
ACCEPTANCE_AUTHORITY = {
    "can_authorize_execution": False,
    "requires_separate_authorization": True,
}


class AcceptanceArtifactError(ValueError):
    """Raised when an acceptance artifact cannot be built deterministically."""


def _now_iso() -> str:
    """Audit timestamp only; never part of the hashed identity."""
    return datetime.now(timezone.utc).isoformat()


def _acceptance_id(acceptance_sha256: str) -> str:
    """Deterministic identity: acceptance-<first 16 hex of the hash>."""
    return f"acceptance-{acceptance_sha256[:16]}"


@dataclass(frozen=True)
class AcceptanceArtifact:
    """Immutable acceptance record binding the full evidence chain.

    The artifact proves: task -> frozen evidence -> validated reviews ->
    normalized findings -> consensus evaluation -> terminal disposition ->
    acceptance. No field carries execution authority, state, ledger, or DB id.
    """

    acceptance_id: str
    task_id: str
    evidence_package_id: str
    consensus_id: str
    finding_set_sha256: str
    evaluation_sha256: str
    disposition_sha256: str
    disposition: str
    reason_codes: tuple[str, ...]
    relevant_finding_keys: tuple[str, ...]
    blocking_finding_keys: tuple[str, ...]
    blocking_severities: tuple[str, ...]
    review_ids: tuple[str, ...]
    finding_keys: tuple[str, ...]
    accepted_at: str
    authority: dict[str, Any]
    acceptance_sha256: str

    @property
    def is_accepted(self) -> bool:
        return self.disposition == DISPOSITION_ACCEPTED

    def as_document(self) -> dict[str, Any]:
        # `accepted_at` is required by the hermes.acceptance schema for
        # downstream consumption; it is audit metadata and is intentionally
        # excluded from `_acceptance_document` (the deterministic hashed shape).
        return {
            **_acceptance_document(self),
            "accepted_at": self.accepted_at,
            "acceptance_sha256": self.acceptance_sha256,
        }


def _acceptance_document(artifact: AcceptanceArtifact) -> dict[str, Any]:
    """Canonical pre-hash shape. The sole source of the public document too.

    Includes ``acceptance_id`` (deterministic once derived) but excludes
    ``acceptance_sha256`` (set after hashing) and ``accepted_at`` (audit
    timestamp, never part of the deterministic hashed identity). Field and
    collection ordering is fixed so the hash is deterministic.
    """
    return {
        "acceptance_id": artifact.acceptance_id,
        "task_id": artifact.task_id,
        "evidence_package_id": artifact.evidence_package_id,
        "consensus_id": artifact.consensus_id,
        "finding_set_sha256": artifact.finding_set_sha256,
        "evaluation_sha256": artifact.evaluation_sha256,
        "disposition_sha256": artifact.disposition_sha256,
        "disposition": artifact.disposition,
        "reason_codes": list(artifact.reason_codes),
        "relevant_finding_keys": list(artifact.relevant_finding_keys),
        "blocking_finding_keys": list(artifact.blocking_finding_keys),
        "blocking_severities": list(artifact.blocking_severities),
        "review_ids": list(artifact.review_ids),
        "finding_keys": list(artifact.finding_keys),
        "authority": dict(artifact.authority),
    }


def _acceptance_core(artifact: AcceptanceArtifact) -> dict[str, Any]:
    """Hashed shape without ``acceptance_id``, used to derive the id itself."""
    document = dict(_acceptance_document(artifact))
    document.pop("acceptance_id", None)
    return document


class AcceptanceArtifactBuilder:
    """Construct an immutable acceptance artifact from a verified 6C disposition."""

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Any = None) -> None:
        # `base_dir` is accepted for API symmetry with the other engines but is
        # unused: 6D performs no filesystem access of its own.
        self.catalog = catalog

    def build(
        self,
        disposition: ConsensusDisposition,
        evaluation: ConsensusEvaluation,
        finding_set: NormalizedFindingSet,
    ) -> AcceptanceArtifact:
        if not isinstance(disposition, ConsensusDisposition):
            raise AcceptanceArtifactError("Acceptance requires a ConsensusDisposition")
        if not isinstance(evaluation, ConsensusEvaluation):
            raise AcceptanceArtifactError("Acceptance requires a ConsensusEvaluation")
        if not isinstance(finding_set, NormalizedFindingSet):
            raise AcceptanceArtifactError("Acceptance requires a NormalizedFindingSet")

        # --- identity binding: all three layers must refer to the same task
        # and frozen evidence package. ---
        if not (
            finding_set.task_id == evaluation.task_id == disposition.task_id
            and finding_set.evidence_package_id
            == evaluation.evidence_package_id
            == disposition.evidence_package_id
        ):
            raise AcceptanceArtifactError(
                "Disposition, evaluation, and finding set do not bind to the "
                "same task/evidence package"
            )

        # --- re-derive every upstream hash rather than trusting the caller. ---
        if finding_set.finding_set_sha256 != sha256_payload(
            _finding_set_document(finding_set)
        ):
            raise AcceptanceArtifactError("Normalized finding set hash does not verify")
        if evaluation.evaluation_sha256 != sha256_payload(_evaluation_document(evaluation)):
            raise AcceptanceArtifactError("Consensus evaluation hash does not verify")
        if disposition.disposition_sha256 != sha256_payload(
            _disposition_document(disposition)
        ):
            raise AcceptanceArtifactError("Consensus disposition hash does not verify")

        # --- chain links: each layer must reference the one beneath it. ---
        if evaluation.finding_set_sha256 != finding_set.finding_set_sha256:
            raise AcceptanceArtifactError(
                "Evaluation does not reference the matching finding set hash"
            )
        if disposition.finding_set_sha256 != finding_set.finding_set_sha256:
            raise AcceptanceArtifactError(
                "Disposition does not reference the matching finding set hash"
            )
        if disposition.evaluation_sha256 != evaluation.evaluation_sha256:
            raise AcceptanceArtifactError(
                "Disposition does not reference the matching evaluation hash"
            )

        # --- eligibility: only ACCEPTED may produce an acceptance artifact. ---
        if disposition.disposition != ACCEPTANCE_ELIGIBLE_DISPOSITION:
            raise AcceptanceArtifactError(
                f"Disposition {disposition.disposition!r} is not eligibility for "
                "acceptance; only ACCEPTED may produce an acceptance artifact"
            )

        finding_keys = tuple(sorted(f.finding_key for f in finding_set.findings))
        accepted_at = _now_iso()

        # Build the artifact without id/hash, derive the id from the
        # hash-stable core, then set the final hash over the full document.
        artifact = AcceptanceArtifact(
            acceptance_id="",
            task_id=disposition.task_id,
            evidence_package_id=disposition.evidence_package_id,
            consensus_id=disposition.disposition_sha256,
            finding_set_sha256=disposition.finding_set_sha256,
            evaluation_sha256=disposition.evaluation_sha256,
            disposition_sha256=disposition.disposition_sha256,
            disposition=disposition.disposition,
            reason_codes=tuple(sorted(disposition.reason_codes)),
            relevant_finding_keys=tuple(sorted(disposition.relevant_finding_keys)),
            blocking_finding_keys=tuple(sorted(disposition.blocking_finding_keys)),
            blocking_severities=tuple(sorted(disposition.blocking_severities)),
            review_ids=tuple(sorted(evaluation.review_ids)),
            finding_keys=finding_keys,
            accepted_at=accepted_at,
            authority=dict(ACCEPTANCE_AUTHORITY),
            acceptance_sha256="",
        )
        acceptance_id = _acceptance_id(sha256_payload(_acceptance_core(artifact)))
        artifact = replace(artifact, acceptance_id=acceptance_id)
        acceptance_sha256 = sha256_payload(_acceptance_document(artifact))
        return replace(artifact, acceptance_sha256=acceptance_sha256)
