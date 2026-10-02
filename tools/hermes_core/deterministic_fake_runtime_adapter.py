"""EA-4D.3C: deterministic in-memory fake runtime launch adapter.

This is the ONLY adapter implementation authorized in this slice, and it is a
*deterministic, in-memory simulation*. It performs no subprocess, no network,
no filesystem discovery, no environment inspection, and no external runtime
call. Direct calls are authorized in isolated tests only; no production
coordinator may invoke it here (that belongs to EA-4D.3D).

Controlling invariant (frozen):

    LAUNCH_ATTEMPT_RECORDED != WORKER STARTED

A fake ``RuntimeLaunchOutcome.STARTED`` is a simulated positive acknowledgement
and does NOT authorize a real worker start, a durable ``EXECUTING`` state, or
any external request. The fake never persists ``ExecutionStartResult``, never
writes the Start DB / Authority DB, and never mutates the LaunchAttempt, the
binding, or any route/Authority artifact.

Idempotency: the fake consumes the canonical EA-4D.3B idempotency key. The same
key + same immutable lineage maps to the same logical fake operation; the same
key with conflicting lineage fails closed as ``RuntimeAdapterConflictError``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from tools.hermes_core.execution_start import (
    ExecutionLaunchAttempt,
    WorkerRuntimeBinding,
)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeAdapterConflictError,
    RuntimeAdapterValidationError,
    RuntimeLaunchAdapter,
    RuntimeLaunchOutcome,
    RuntimeLaunchResult,
    RuntimeLookupOutcome,
    RuntimeLookupResult,
)


def _stable_run_id(idempotency_key: str) -> str:
    """Deterministic, replay-stable runtime run identifier.

    No random UUID per replay (EA-4D.3C packet Section 15). Same key -> same id.
    """
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
    return f"fake-run-{digest}"


def _lineage(launch_attempt: ExecutionLaunchAttempt):
    """Immutable lineage tuple used for same-key conflict detection."""
    return (
        launch_attempt.launch_attempt_id,
        launch_attempt.reservation_id,
        launch_attempt.reservation_hash,
        launch_attempt.route_id,
        launch_attempt.route_hash,
    )


@dataclass(frozen=True)
class FakeLaunchScript:
    """Explicit, deterministic, typed fake behavior.

    No arbitrary callable/lambda execution is accepted (EA-4D.3C Sections 48-49).
    Tests configure typed scripted outcomes only.

    ``launch_outcome`` selects the simulated launch result.
    ``timeout_after_send`` and ``lost_response`` force UNKNOWN (ambiguous post-
        delivery).
    ``raise_pre_delivery`` forces a definitive pre-delivery validation failure
        (-> FAILED).
    ``raise_post_delivery`` forces an ambiguous post-delivery exception
        (-> UNKNOWN).
    ``lookup_outcome`` optionally scripts an ambiguous lookup result (UNKNOWN);
        otherwise lookup reflects the recorded launch outcome.
    """

    launch_outcome: RuntimeLaunchOutcome = RuntimeLaunchOutcome.STARTED
    error_code: Optional[str] = None
    error_summary: Optional[str] = None
    timeout_after_send: bool = False
    lost_response: bool = False
    raise_pre_delivery: bool = False
    raise_post_delivery: bool = False
    lookup_outcome: Optional[RuntimeLookupOutcome] = None


@dataclass
class _RecordedRun:
    lineage: tuple
    runtime_run_id: str
    result: RuntimeLaunchResult


class DeterministicFakeRuntimeAdapter:
    """Deterministic in-memory fake implementing ``RuntimeLaunchAdapter``.

    Keeps only its own in-memory protocol state (per-key logical runs + their
    recorded outcomes). Thread-safety/concurrency is intentionally minimal;
    the optional modest concurrency test (10 callers, same key) requires exactly
    one logical run and a stable runtime_run_id.
    """

    def __init__(self, script: Optional[FakeLaunchScript] = None) -> None:
        self._script = script or FakeLaunchScript()
        self._runs: dict[str, _RecordedRun] = {}
        self.invocation_count: int = 0
        self.logical_run_count: int = 0

    # -- RuntimeLaunchAdapter contract ------------------------------------ #
    def launch(
        self,
        *,
        binding: WorkerRuntimeBinding,
        launch_attempt: ExecutionLaunchAttempt,
        idempotency_key: str,
    ) -> RuntimeLaunchResult:
        if binding is None or launch_attempt is None or not idempotency_key:
            raise RuntimeAdapterValidationError(
                "launch requires a resolved binding, an admitted LaunchAttempt, "
                "and a non-empty canonical idempotency key")
        # The caller-supplied idempotency key MUST equal the canonical key
        # carried by the admitted LaunchAttempt. The adapter never accepts an
        # alternate key (no caller override of launch identity).
        if idempotency_key != launch_attempt.idempotency_key:
            raise RuntimeAdapterValidationError(
                "idempotency_key does not match ExecutionLaunchAttempt."
                "idempotency_key; caller override of launch identity rejected")
        if not binding.enabled:
            raise RuntimeAdapterValidationError("binding is not enabled")
        if not binding.supports_idempotency:
            raise RuntimeAdapterValidationError(
                "binding does not support idempotency; refusing launch")
        if launch_attempt.operation not in (binding.allowed_operations or []):
            raise RuntimeAdapterValidationError(
                "operation not permitted by binding; no routing drift allowed")

        lineage = _lineage(launch_attempt)
        self.invocation_count += 1

        # Definitive pre-delivery rejection -> FAILED (not UNKNOWN).
        if self._script.raise_pre_delivery:
            raise RuntimeAdapterValidationError(
                self._script.error_summary or "pre-delivery validation rejected")

        existing = self._runs.get(idempotency_key)
        if existing is not None:
            if existing.lineage != lineage:
                raise RuntimeAdapterConflictError(
                    f"idempotency key {idempotency_key!r} already maps to a "
                    f"different immutable launch lineage; fail closed")
            runtime_run_id = existing.runtime_run_id
        else:
            runtime_run_id = _stable_run_id(idempotency_key)
            self.logical_run_count += 1

        # Ambiguous post-delivery exception -> UNKNOWN (never a retry here).
        if self._script.raise_post_delivery:
            result = RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.UNKNOWN,
                runtime_run_id=runtime_run_id,
                error_code=self._script.error_code or "POST_DELIVERY_AMBIGUOUS",
                error_summary=self._script.error_summary
                or "ambiguous exception after simulated delivery",
            )
            self._runs[idempotency_key] = _RecordedRun(lineage, runtime_run_id, result)
            return result

        # Ambiguous post-delivery timing -> UNKNOWN.
        if self._script.timeout_after_send or self._script.lost_response:
            result = RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.UNKNOWN,
                runtime_run_id=runtime_run_id,
                error_code=self._script.error_code or "ACK_LOST",
                error_summary=self._script.error_summary
                or "acknowledgement lost after simulated send",
            )
            self._runs[idempotency_key] = _RecordedRun(lineage, runtime_run_id, result)
            return result

        outcome = self._script.launch_outcome
        if outcome == RuntimeLaunchOutcome.STARTED:
            result = RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.STARTED,
                runtime_run_id=runtime_run_id,  # required, stable, non-empty
                adapter_metadata_hash=None,
            )
        elif outcome == RuntimeLaunchOutcome.FAILED:
            result = RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.FAILED,
                runtime_run_id=None,  # definitive non-start: normally absent
                error_code=self._script.error_code or "SCRIPTED_REJECTION",
                error_summary=self._script.error_summary,
            )
        else:  # UNKNOWN
            result = RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.UNKNOWN,
                runtime_run_id=runtime_run_id,
                error_code=self._script.error_code,
                error_summary=self._script.error_summary,
            )
        self._runs[idempotency_key] = _RecordedRun(lineage, runtime_run_id, result)
        return result

    def lookup(self, idempotency_key: str) -> RuntimeLookupResult:
        if not idempotency_key:
            raise RuntimeAdapterLookupError("idempotency_key required for lookup")
        recorded = self._runs.get(idempotency_key)
        if recorded is None:
            # Fake can prove no logical operation exists for this key.
            return RuntimeLookupResult(outcome=RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE)
        # Scripted ambiguous lookup overrides with UNKNOWN when configured.
        if self._script.lookup_outcome is not None:
            return RuntimeLookupResult(outcome=self._script.lookup_outcome)
        outcome = recorded.result.outcome
        if outcome == RuntimeLaunchOutcome.STARTED:
            return RuntimeLookupResult(
                outcome=RuntimeLookupOutcome.FOUND_STARTED,
                runtime_run_id=recorded.runtime_run_id,
            )
        if outcome == RuntimeLaunchOutcome.FAILED:
            return RuntimeLookupResult(
                outcome=RuntimeLookupOutcome.FOUND_FAILED,
                error_code=recorded.result.error_code,
                error_summary=recorded.result.error_summary,
            )
        return RuntimeLookupResult(
            outcome=RuntimeLookupOutcome.UNKNOWN,
            runtime_run_id=recorded.runtime_run_id,
            error_code=recorded.result.error_code,
            error_summary=recorded.result.error_summary,
        )

    # -- introspection (tests only) --------------------------------------- #
    def recorded_runtime_run_id(self, idempotency_key: str) -> Optional[str]:
        rec = self._runs.get(idempotency_key)
        return rec.runtime_run_id if rec is not None else None
