"""Receiver-neutral governed adapter protocol.

Minimal contract for any governed receiver. Deliberately transport-agnostic.
No Codex-specific types. No arbitrary exec. No generic process API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, Sequence, Tuple, runtime_checkable


class ReceiverError(RuntimeError): pass
class BinaryVerificationError(ReceiverError): pass
class TransportQualificationError(ReceiverError): pass
class ReceiverProcessError(ReceiverError): pass
class ReceiverTimeoutError(ReceiverError): pass
class ReceiverCancelledError(ReceiverError): pass
class ReceiverParseError(ReceiverError): pass
class ReceiverStartStateUnknownError(ReceiverError): pass
class ReceiverReplayConflictError(ReceiverError): pass
class ReceiverExecutionNotAuthorizedError(ReceiverError): pass


@dataclass(frozen=True)
class BinaryIdentity:
    sha256: str
    version: str
    executable: str
    size_bytes: int
    metadata_probe_spawned: bool = True


@dataclass(frozen=True)
class QualifiedRuntimeBinding:
    executable: str
    binary_sha256: str
    binary_version: str
    transport_contract_id: str


@dataclass(frozen=True)
class ProcessResult:
    pid: int
    returncode: int
    stdout: str
    stderr: str
    final_output: str = ""
    timed_out: bool = False
    cancelled: bool = False
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class InvocationRecord:
    idempotency_key: str
    runtime_run_id: str
    start_state: str
    terminal_state: Optional[str]
    pid: Optional[int]
    argv_hash: str


@dataclass(frozen=True)
class VerifiedResult:
    valid: bool
    payload: dict[str, Any]
    parse_error: Optional[str] = None


@dataclass(frozen=True)
class ExecutionOutcome:
    process_started: bool
    replayed: bool
    record: InvocationRecord
    verified_result: Optional[VerifiedResult]


@runtime_checkable
class ReceiverAdapter(Protocol):
    """Governed receiver adapter protocol — receiver-neutral."""

    @property
    def receiver_id(self) -> str: ...
    @property
    def receiver_version(self) -> str: ...
    @property
    def adapter_version(self) -> str: ...

    def verify_binary(self) -> BinaryIdentity: ...
    def qualify_runtime(self) -> QualifiedRuntimeBinding: ...
    def qualify_schema_contract(self) -> dict[str, Any]: ...
    def build_argv(self, runtime_run_id: str) -> Sequence[str]: ...
    def parse_output(self, stdout: str) -> dict[str, Any]: ...
    def classify_start_state(
        self, pid: Optional[int], result: Optional[ProcessResult]
    ) -> str: ...
    def prepare_invocation(
        self, *, idempotency_key: str, launch_attempt_id: str,
        delegation_id: str, stdin_data: str,
    ) -> Tuple[InvocationRecord, Sequence[str], bool]: ...
    def execute(
        self, *, idempotency_key: str, launch_attempt_id: str,
        delegation_id: str, stdin_data: str,
    ) -> ExecutionOutcome: ...
