"""EA-4D.4F Regional Hand Repair pilot composition root.

This is the workload-specific pilot composition root authorized by R1-P1.
It is NOT a generic execution API. It is limited to:
- One workload: REGIONAL_HAND_REPAIR
- One worker: regional-hand-repair-worker
- One operation: one bounded regional SDXL inpaint repair

Design source of truth:
    EA-4D.4F-R6-CANONICAL_PILOT_CONTRACT.md
    EA-4D.4F-R1-P1_design_report.md

Authority limits:
    CPU-only. No GPU, no ComfyUI client, no submission.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional

from tools.regional_hand_repair_evidence import RegionalHandRepairEvidenceStore
from tools.regional_hand_repair_submission import RegionalHandRepairSubmissionOrchestrator
from tools.regional_hand_repair_verification import RegionalHandRepairVerificationOrchestrator
from tools.regional_hand_repair_cleanup import RegionalHandRepairCleanupOrchestrator
from tools.regional_hand_repair_adapter import RegionalHandRepairComfyUIAdapter
from tools.regional_hand_repair_workflow import build_frozen_template


# ---------------------------------------------------------------------------
# Pilot configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PilotConfig:
    """Configuration for the Regional Hand Repair pilot."""
    enabled: bool = False
    evidence_db_path: Optional[str] = None
    comfyui_endpoint: str = "http://127.0.0.1:8188"

    def is_active(self) -> bool:
        return self.enabled


# ---------------------------------------------------------------------------
# Pilot composition root
# ---------------------------------------------------------------------------


class RegionalHandRepairPilotRoot:
    """Pilot composition root for Regional Hand Repair.

    This root owns orchestration ONLY. It does NOT own:
    - authorization truth
    - route truth
    - runtime-binding truth
    - StartResult truth
    - EXECUTING projection truth
    - GPU authority truth
    - repair validation truth

    Those remain with their existing authoritative components.
    """

    def __init__(self, config: PilotConfig) -> None:
        self._config = config
        self._evidence_store: Optional[RegionalHandRepairEvidenceStore] = None
        self._submission_orchestrator: Optional[RegionalHandRepairSubmissionOrchestrator] = None
        self._verification_orchestrator: Optional[RegionalHandRepairVerificationOrchestrator] = None
        self._cleanup_orchestrator: Optional[RegionalHandRepairCleanupOrchestrator] = None

    @property
    def is_active(self) -> bool:
        return self._config.is_active()

    def dispatch_authorized_post_launch(
        self,
        *,
        launch_attempt_id: str,
        dispatcher: Any,
    ) -> Any:
        """Hand an authority-created launch ID to the gated 4E dispatcher.

        The pilot consumes the supplied identity exactly as received. It does
        not derive, replace, persist, retry, or otherwise claim ownership of
        the launch-attempt identity or any downstream authority transition.
        """
        if not self.is_active:
            raise RuntimeError("regional hand repair pilot is disabled")
        if not launch_attempt_id:
            raise ValueError("launch_attempt_id is required")
        return dispatcher.dispatch_post_launch(launch_attempt_id)

    def _get_evidence_store(self) -> RegionalHandRepairEvidenceStore:
        if self._evidence_store is None:
            db_path = self._config.evidence_db_path
            if db_path is None:
                db_path = os.path.join(tempfile.gettempdir(), "regional_hand_repair.db")
            self._evidence_store = RegionalHandRepairEvidenceStore(db_path)
        return self._evidence_store

    def _get_submission_orchestrator(self) -> RegionalHandRepairSubmissionOrchestrator:
        if self._submission_orchestrator is None:
            store = self._get_evidence_store()
            adapter = RegionalHandRepairComfyUIAdapter()
            self._submission_orchestrator = RegionalHandRepairSubmissionOrchestrator(store, adapter)
        return self._submission_orchestrator

    def _get_verification_orchestrator(self) -> RegionalHandRepairVerificationOrchestrator:
        if self._verification_orchestrator is None:
            self._verification_orchestrator = RegionalHandRepairVerificationOrchestrator()
        return self._verification_orchestrator

    def _get_cleanup_orchestrator(self) -> RegionalHandRepairCleanupOrchestrator:
        if self._cleanup_orchestrator is None:
            store = self._get_evidence_store()
            self._cleanup_orchestrator = RegionalHandRepairCleanupOrchestrator(store)
        return self._cleanup_orchestrator

    def close(self) -> None:
        if self._evidence_store is not None:
            self._evidence_store.close()


def create_pilot_root(
    *,
    enabled: bool = False,
    evidence_db_path: Optional[str] = None,
) -> RegionalHandRepairPilotRoot:
    """Factory function to create a pilot composition root."""
    config = PilotConfig(
        enabled=enabled,
        evidence_db_path=evidence_db_path,
    )
    return RegionalHandRepairPilotRoot(config)
