"""EA-4D.4A: ExecutionStartResult persistence service (authority-side bridge).

This module converts verified runtime launch evidence into one durable,
replay-safe, lineage-bound ``ExecutionStartResult``. It is the authority-side
bridge between the mechanics layer (EA-4D.3E real runtime) and the durable
``ExecutionStartResult persisted`` stage of the EA-4D governance boundary:

    LAUNCH_ATTEMPT_RECORDED
        != WORKER STARTED
        != ExecutionStartResult persisted
        != EXECUTING

Design discipline (frozen EA-4D.4 design):
- The service possesses LOOKUP capability only (via ``RuntimeStartLookup``).
  It does NOT possess launch capability; it never calls ``adapter.launch()``,
  ``subprocess``, or any network. The read-only lookup dependency is injected
  explicitly (trusted construction) and is decoupled from any concrete adapter
  registry, so a future frozen adapter kind reaches this bridge without coupling.
- ``UNKNOWN`` and ``NOT_FOUND_AUTHORITATIVE`` create NO ``ExecutionStartResult``.
- A transient pre-delivery FAILED may be persisted while evidence is present;
  if lost before persistence, reconciliation returns ``NOT_FOUND_AUTHORITATIVE``
  and the launch stays unresolved (no fabricated FAILED).
- Results are immutable after insert; conflicting evidence fails closed.

It does NOT:
* transition into ``EXECUTING`` (EA-4D.4B, not authorized here);
* invoke any runtime, create a LaunchAttempt, or perform any subprocess/network.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from tools.hermes_core.execution_start import (
    ExecutionStartOutcome,
    ExecutionStartResult,
    ExecutionStartResultConflictError,
    ExecutionStartResultError,
    build_execution_start_result,
)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeLookupOutcome,
    RuntimeLookupResult,
)
from tools.hermes_core.sqlite_execution_start_store import (
    SQLiteExecutionStartStore,
)


# --------------------------------------------------------------------------- #
# Verified runtime evidence (does NOT itself imply persistence)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VerifiedRuntimeStartEvidence:
    """Frozen, verified runtime start evidence presented to the service.

    ``source`` and ``observed_at`` are provenance/timing metadata and are
    excluded from canonical evidence identity. ``error_summary`` is non-identity,
    integrity-bound metadata.
    """

    launch_attempt_id: str
    idempotency_key: str
    runtime_outcome: ExecutionStartOutcome
    runtime_run_id: Optional[str]
    source: str  # "launch" | "reconciliation"
    runtime_adapter_kind: str
    runtime_adapter_version: str
    observed_at: str
    evidence_hash: str
    error_code: Optional[str] = None
    error_summary: Optional[str] = None


# --------------------------------------------------------------------------- #
# Read-only lookup dependency (decoupled from concrete adapter registries)
# --------------------------------------------------------------------------- #


class RuntimeStartLookup(Protocol):
    """Read-only reconciliation dependency for the 4A authority bridge.

    The service may call ``lookup(canonical idempotency key)`` only. The
    Protocol exposes NO launch/invocation method, guaranteeing the service
    possesses lookup capability but not launch capability.
    """

    def lookup(self, idempotency_key: str) -> RuntimeLookupResult:
        ...  # pragma: no cover


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class ExecutionStartResultService:
    """Persist verified runtime start evidence as immutable ExecutionStartResult.

    The service loads durable lineage from the store, verifies it independently,
    matches runtime evidence to that lineage, and persists the first definitive
    result. Reconciliation reuses the injected read-only ``RuntimeStartLookup``.
    """

    def __init__(
        self,
        store: SQLiteExecutionStartStore,
        lookup: RuntimeStartLookup,
    ) -> None:
        # Explicit trusted construction: store + read-only lookup dependency.
        self._store = store
        self._lookup = lookup

    # -- hashing -------------------------------------------------------------
    @staticmethod
    def runtime_evidence_hash(
        *,
        launch_attempt_id: str,
        idempotency_key: str,
        runtime_outcome: ExecutionStartOutcome,
        runtime_run_id: Optional[str],
        runtime_adapter_kind: str,
        runtime_adapter_version: str,
        error_code: Optional[str],
    ) -> str:
        """Canonical runtime-evidence identity hash (frozen EA-4D.4).

        Excludes: ``source``, ``observed_at``, ``error_summary``.
        """
        from tools.hermes_core.hashing import sha256_payload
        return sha256_payload({
            "schema": "ea4d4-runtime-evidence-v1",
            "launch_attempt_id": launch_attempt_id,
            "idempotency_key": idempotency_key,
            "runtime_outcome": runtime_outcome.value,
            "runtime_run_id": runtime_run_id or "",
            "runtime_adapter_kind": runtime_adapter_kind,
            "runtime_adapter_version": runtime_adapter_version,
            "error_code": error_code or "",
        })

    # -- persistence from direct evidence -----------------------------------
    def persist_start_result(
        self,
        attempt,  # ExecutionLaunchAttempt (durable, verified)
        reservation,  # ExecutionStartReservation (durable, verified)
        evidence: VerifiedRuntimeStartEvidence,
    ) -> ExecutionStartResult:
        """Persist a result from verified direct runtime evidence.

        Returns the persisted (or existing idempotent) result. Raises
        ExecutionStartResultConflictError on conflicting evidence.
        """
        self._verify_lineage(attempt, reservation, evidence)
        if evidence.runtime_outcome == ExecutionStartOutcome.UNKNOWN:
            # UNKNOWN creates no result; launch stays unresolved.
            raise ExecutionStartResultError(
                "UNKNOWN runtime evidence does not create an ExecutionStartResult")
        if evidence.runtime_outcome == ExecutionStartOutcome.STARTED and not evidence.runtime_run_id:
            raise ExecutionStartResultError(
                "STARTED requires a stable non-empty runtime_run_id")
        if evidence.runtime_outcome == ExecutionStartOutcome.FAILED and not evidence.error_code:
            raise ExecutionStartResultError(
                "FAILED requires a definitive error_code")
        result = build_execution_start_result(
            launch_attempt_id=attempt.launch_attempt_id,
            launch_attempt_hash=attempt.artifact_hash,
            reservation_id=reservation.reservation_id,
            reservation_hash=reservation.artifact_hash,
            route_id=attempt.route_id,
            route_hash=attempt.route_hash,
            task_id=attempt.task_id,
            worker_id=attempt.worker_id,
            worker_version=attempt.worker_version,
            runtime_binding_id=attempt.runtime_binding_id,
            runtime_binding_version=attempt.runtime_binding_version,
            runtime_binding_hash=attempt.runtime_binding_hash,
            idempotency_key=attempt.idempotency_key,
            outcome=evidence.runtime_outcome,
            recorded_at=evidence.observed_at or _now_rfc3339(),
            runtime_evidence_hash=evidence.evidence_hash,
            runtime_run_id=evidence.runtime_run_id,
            error_code=evidence.error_code,
            error_summary=evidence.error_summary,
        )
        self._store.persist_execution_start_result(result)
        return result

    # -- read-only reconciliation -------------------------------------------
    def reconcile_start_result(self, launch_attempt_id: str) -> Optional[ExecutionStartResult]:
        """Reconcile a launch attempt by read-only lookup of its idempotency key.

        FOUND_STARTED -> persist STARTED; FOUND_FAILED -> persist FAILED;
        NOT_FOUND_AUTHORITATIVE / UNKNOWN -> unresolved (no result).
        Crash A1/A2/A3 semantics apply; never launches runtime.
        """
        # Load durable attempt to obtain the canonical idempotency key + lineage.
        attempt = self._store.get_execution_launch_attempt(launch_attempt_id)
        if attempt is None:
            raise ExecutionStartResultError(
                f"unknown launch_attempt_id={launch_attempt_id!r}")
        reservation = self._store.get_execution_start_reservation(
            attempt.reservation_id)
        if reservation is None:
            raise ExecutionStartResultError(
                f"unknown reservation_id={attempt.reservation_id!r}")
        existing = self._store.get_execution_start_result(launch_attempt_id)
        if existing is not None:
            return existing  # already persisted; idempotent
        looked = self._lookup.lookup(attempt.idempotency_key)
        if looked.outcome == RuntimeLookupOutcome.FOUND_STARTED:
            evidence = VerifiedRuntimeStartEvidence(
                launch_attempt_id=attempt.launch_attempt_id,
                idempotency_key=attempt.idempotency_key,
                runtime_outcome=ExecutionStartOutcome.STARTED,
                runtime_run_id=looked.runtime_run_id,
                source="reconciliation",
                runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
                runtime_adapter_version="1",
                observed_at=_now_rfc3339(),
                evidence_hash=self.runtime_evidence_hash(
                    launch_attempt_id=attempt.launch_attempt_id,
                    idempotency_key=attempt.idempotency_key,
                    runtime_outcome=ExecutionStartOutcome.STARTED,
                    runtime_run_id=looked.runtime_run_id,
                    runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
                    runtime_adapter_version="1",
                    error_code=None,
                ),
                error_code=None,
                error_summary=None,
            )
            return self.persist_start_result(attempt, reservation, evidence)
        if looked.outcome == RuntimeLookupOutcome.FOUND_FAILED:
            evidence = VerifiedRuntimeStartEvidence(
                launch_attempt_id=attempt.launch_attempt_id,
                idempotency_key=attempt.idempotency_key,
                runtime_outcome=ExecutionStartOutcome.FAILED,
                runtime_run_id=looked.runtime_run_id,
                source="reconciliation",
                runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
                runtime_adapter_version="1",
                observed_at=_now_rfc3339(),
                evidence_hash=self.runtime_evidence_hash(
                    launch_attempt_id=attempt.launch_attempt_id,
                    idempotency_key=attempt.idempotency_key,
                    runtime_outcome=ExecutionStartOutcome.FAILED,
                    runtime_run_id=looked.runtime_run_id,
                    runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
                    runtime_adapter_version="1",
                    error_code=looked.error_code,
                ),
                error_code=looked.error_code,
                error_summary=looked.error_summary,
            )
            return self.persist_start_result(attempt, reservation, evidence)
        # NOT_FOUND_AUTHORITATIVE or UNKNOWN -> unresolved; no result.
        return None

    # -- lineage verification -----------------------------------------------
    def _verify_lineage(self, attempt, reservation, evidence) -> None:
        if not attempt.verify_hash():
            raise ExecutionStartResultError("launch attempt hash verification failed")
        if not reservation.verify_hash():
            raise ExecutionStartResultError("reservation hash verification failed")
        if evidence.launch_attempt_id != attempt.launch_attempt_id:
            raise ExecutionStartResultError("evidence launch_attempt_id mismatch")
        if evidence.idempotency_key != attempt.idempotency_key:
            raise ExecutionStartResultError("evidence idempotency_key mismatch")
        if attempt.reservation_id != reservation.reservation_id:
            raise ExecutionStartResultError("attempt/reservation linkage mismatch")


def _now_rfc3339() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
