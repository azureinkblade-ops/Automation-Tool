"""Record validated Hermes state transitions into the local event ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .hashing import sha256_payload
from .ledger import EventLedger, LedgerEntry
from .schemas import SchemaCatalog
from .state_machine import ArtifactBundle, TransitionResult, validate_transition


@dataclass(frozen=True)
class RecordedTransition:
    result: TransitionResult
    ledger_entry: LedgerEntry


class TransitionRecorder:
    """Validate a transition, then append one authoritative ledger event."""

    def __init__(self, ledger: EventLedger, catalog: SchemaCatalog) -> None:
        self.ledger = ledger
        self.catalog = catalog

    def record_transition(
        self,
        from_state: str,
        to_state: str,
        task_id: str,
        artifacts: ArtifactBundle,
        *,
        actor: str = "hermes",
        occurred_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RecordedTransition:
        result = validate_transition(from_state, to_state, artifacts, self.catalog)
        payload = {
            "from_state": from_state,
            "to_state": to_state,
            "task_id": task_id,
            "actor": actor,
            "artifact_refs": _artifact_refs(artifacts),
            "metadata": metadata or {},
            "transition_sha256": sha256_payload(
                {
                    "from_state": from_state,
                    "to_state": to_state,
                    "task_id": task_id,
                    "artifact_refs": _artifact_refs(artifacts),
                }
            ),
        }
        entry = self.ledger.append(
            "governance.transition.accepted",
            task_id,
            payload,
            occurred_at=occurred_at,
        )
        return RecordedTransition(result=result, ledger_entry=entry)

    def replay_latest_states(self) -> dict[str, str]:
        states: dict[str, str] = {}
        for entry in self.ledger.replay():
            if entry.event_type != "governance.transition.accepted":
                continue
            task_id = str(entry.payload.get("task_id") or entry.task_id)
            to_state = entry.payload.get("to_state")
            if isinstance(to_state, str):
                states[task_id] = to_state
        return states

    def latest_state(self, task_id: str) -> str | None:
        return self.replay_latest_states().get(task_id)


def _artifact_refs(artifacts: ArtifactBundle) -> dict[str, Any]:
    refs: dict[str, Any] = {
        "event_parent_ref": artifacts.event_parent_ref,
    }
    if artifacts.task:
        refs["task_id"] = artifacts.task.get("task_id")
    if artifacts.evidence:
        refs["evidence_package_id"] = artifacts.evidence.get("evidence_package_id")
        refs["evidence_sha256"] = artifacts.evidence.get("package_sha256")
    if artifacts.consensus:
        refs["consensus_id"] = artifacts.consensus.get("consensus_id")
        refs["consensus_result"] = artifacts.consensus.get("result")
    if artifacts.acceptance:
        refs["acceptance_id"] = artifacts.acceptance.get("acceptance_id")
        refs["acceptance_sha256"] = artifacts.acceptance.get("acceptance_sha256")
    if artifacts.authorization:
        refs["authorization_id"] = artifacts.authorization.get("authorization_id")
        refs["authorization_sha256"] = artifacts.authorization.get("authorization_sha256")
        refs["parent_acceptance_sha256"] = artifacts.authorization.get("parent_acceptance_sha256")
    if artifacts.execution:
        refs["execution_id"] = artifacts.execution.get("execution_id")
    if artifacts.reviews:
        refs["review_ids"] = [review.get("review_id") for review in artifacts.reviews]
    return refs
