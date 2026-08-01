"""Record verified Hermes evidence packages into the local event ledger."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import EvidencePackage, EvidencePackageBuilder
from .ledger import EventLedger, LedgerEntry


@dataclass(frozen=True)
class RecordedEvidence:
    evidence: EvidencePackage
    ledger_entry: LedgerEntry


class EvidenceLedgerRecorder:
    """Verify evidence, then append one evidence.frozen ledger event."""

    def __init__(self, ledger: EventLedger, builder: EvidencePackageBuilder) -> None:
        self.ledger = ledger
        self.builder = builder

    def record_frozen_evidence(
        self,
        evidence: EvidencePackage | Path | str,
        *,
        actor: str = "hermes",
        occurred_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RecordedEvidence:
        package = self.builder.load(evidence) if not isinstance(evidence, EvidencePackage) else evidence
        self.builder.verify(package)
        task_id = str(package.document["task_id"])
        payload = {
            "evidence_package_id": package.evidence_package_id,
            "package_sha256": package.package_sha256,
            "package_path": str(package.path) if package.path is not None else None,
            "artifact_count": len(package.document["inventory"]),
            "artifact_ids": [item["artifact_id"] for item in package.document["inventory"]],
            "actor": actor,
            "metadata": metadata or {},
        }
        entry = self.ledger.append(
            "evidence.frozen",
            task_id,
            payload,
            occurred_at=occurred_at,
        )
        return RecordedEvidence(evidence=package, ledger_entry=entry)

    def replay_latest_evidence(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for entry in self.ledger.replay():
            if entry.event_type != "evidence.frozen":
                continue
            latest[entry.task_id] = {
                "task_id": entry.task_id,
                "occurred_at": entry.occurred_at,
                **entry.payload,
            }
        return latest

    def latest_evidence(self, task_id: str) -> dict[str, Any] | None:
        return self.replay_latest_evidence().get(task_id)

