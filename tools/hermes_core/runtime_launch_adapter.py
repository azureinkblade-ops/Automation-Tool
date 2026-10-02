"""EA-4D.3C: typed runtime launch adapter protocol + result/lookup contracts.

This module defines ONLY the typed contracts for launching a *previously
admitted* execution launch attempt against a *resolved* worker runtime binding.
It contains no execution logic and invokes no adapter.

Controlling invariant (frozen by the EA-4D.3C authorization packet):

    LAUNCH_ATTEMPT_RECORDED != WORKER STARTED

A ``RuntimeLaunchOutcome.STARTED`` is a positive acknowledgement from an
adapter, not a durable ``EXECUTING`` projection and not a real worker start.
This module never persists results, never projects EXECUTING, and never
invokes an adapter. The deterministic fake implementation lives in
``deterministic_fake_runtime_adapter.py``.

Reused frozen EA-4D artifacts (do not create competing copies):
    ExecutionLaunchAttempt, WorkerRuntimeBinding
    canonical idempotency-key preimage/semantics (EA-4D.3B)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from tools.hermes_core.execution_start import (
    ExecutionLaunchAttempt,
    WorkerRuntimeBinding,
)


# --------------------------------------------------------------------------- #
# Errors (narrowly scoped to this module; frozen domain hierarchies untouched)
# --------------------------------------------------------------------------- #
class RuntimeAdapterError(Exception):
    """Base error for EA-4D.3C runtime launch adapter contract violations."""


class RuntimeAdapterValidationError(RuntimeAdapterError):
    """Definitive pre-delivery validation failure (-> FAILED, not UNKNOWN)."""


class RuntimeAdapterConflictError(RuntimeAdapterError):
    """Same idempotency key with conflicting immutable lineage (fail closed)."""


class RuntimeAdapterProtocolError(RuntimeAdapterError):
    """Protocol/contract misuse (e.g. malformed result)."""


class RuntimeAdapterLookupError(RuntimeAdapterError):
    """Lookup/reconciliation contract violation."""


# --------------------------------------------------------------------------- #
# Outcomes
# --------------------------------------------------------------------------- #
class RuntimeLaunchOutcome(str, enum.Enum):
    """Exactly three frozen runtime launch outcomes. No fourth implicit state."""

    STARTED = "STARTED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


# --------------------------------------------------------------------------- #
# Immutable launch result
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RuntimeLaunchResult:
    """Immutable result of a single adapter launch attempt.

    Semantics (frozen by EA-4D.3C packet):
        STARTED -> runtime_run_id required (positive acknowledgement)
        FAILED  -> runtime_run_id normally absent (definitive non-start)
        UNKNOWN -> runtime_run_id may be absent or present if observed
    A previously-returned result object is never mutated from UNKNOWN to
    STARTED.
    """

    outcome: RuntimeLaunchOutcome
    runtime_run_id: Optional[str] = None
    error_code: Optional[str] = None
    error_summary: Optional[str] = None
    adapter_metadata_hash: Optional[str] = None


# --------------------------------------------------------------------------- #
# Lookup / reconciliation outcomes
# --------------------------------------------------------------------------- #
class RuntimeLookupOutcome(str, enum.Enum):
    """Frozen reconciliation lookup outcomes."""

    FOUND_STARTED = "FOUND_STARTED"
    FOUND_FAILED = "FOUND_FAILED"
    NOT_FOUND_AUTHORITATIVE = "NOT_FOUND_AUTHORITATIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RuntimeLookupResult:
    """Immutable reconciliation result keyed by canonical idempotency key."""

    outcome: RuntimeLookupOutcome
    runtime_run_id: Optional[str] = None
    error_code: Optional[str] = None
    error_summary: Optional[str] = None


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #
@runtime_checkable
class RuntimeLaunchAdapter(Protocol):
    """Typed contract for launching a previously-admitted launch attempt.

    Required properties (frozen by EA-4D.3C packet):
        - typed inputs
        - already-resolved binding only
        - already-admitted LaunchAttempt only
        - canonical idempotency key only (received, never generated)
        - no caller-supplied alternate worker
        - no caller-supplied alternate operation
        - no caller replacement of idempotency key
        - no routing mutation
        - no second LaunchAttempt creation
        - no Authority state mutation
        - no EXECUTING projection
    """

    def launch(
        self,
        *,
        binding: WorkerRuntimeBinding,
        launch_attempt: ExecutionLaunchAttempt,
        idempotency_key: str,
    ) -> RuntimeLaunchResult:
        """Attempt to launch the already-admitted attempt via the resolved
        binding, returning an immutable typed result. No external execution is
        implied by this contract alone."""
        ...

    def lookup(self, idempotency_key: str) -> RuntimeLookupResult:
        """Reconcile the logical launch identity by its canonical idempotency
        key. Never invokes real runtime, never creates work, never mutates the
        LaunchAttempt, never projects EXECUTING."""
        ...
