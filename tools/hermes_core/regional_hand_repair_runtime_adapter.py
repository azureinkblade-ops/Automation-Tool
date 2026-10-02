"""Constrained HTTP runtime boundary for the regional hand-repair pilot.

No network client is provided here. A transport must be injected explicitly,
which keeps imports and tests side-effect free while enforcing the frozen
ComfyUI endpoint and workflow capability before any delivery attempt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from tools.hermes_core.execution_start import (
    ExecutionLaunchAttempt,
    WorkerRuntimeAdapterKind,
    WorkerRuntimeBinding,
)
from tools.hermes_core.regional_hand_repair_evidence_store import (
    RegionalHandRepairEvidenceStore,
    RepairRun,
)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeAdapterConflictError,
    RuntimeAdapterValidationError,
    RuntimeLaunchOutcome,
    RuntimeLaunchResult,
    RuntimeLookupOutcome,
    RuntimeLookupResult,
)


PILOT_ENDPOINT = "http://127.0.0.1:8188"
PILOT_OPERATION = "regional-hand-repair-inpaint"
PILOT_WORKER_ID = "regional-hand-repair-worker"
PILOT_WORKER_VERSION = "1.0"
PILOT_WORKER_CLASS = "REGIONAL_HAND_REPAIR_WORKER"


class RepairTransport(Protocol):
    endpoint: str

    def submit(self, workflow: Mapping[str, Any], idempotency_key: str) -> str:
        ...

    def lookup(self, idempotency_key: str) -> RuntimeLookupResult:
        ...


@dataclass(frozen=True)
class FrozenRepairWorkflowPolicy:
    template_id: str
    template_sha256: str
    node_allowlist: Mapping[str, str]
    asset_allowlist: Mapping[str, str]


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def validate_repair_workflow_envelope(
    envelope: Mapping[str, Any], policy: FrozenRepairWorkflowPolicy
) -> None:
    required = {
        "template_id",
        "template_sha256",
        "repair_execution_id",
        "task_input_sha256",
        "nodes",
        "assets",
        "workflow",
    }
    if set(envelope) != required:
        raise RuntimeAdapterValidationError(
            f"repair workflow envelope fields differ from frozen contract: {set(envelope)!r}"
        )
    if envelope["template_id"] != policy.template_id:
        raise RuntimeAdapterValidationError("repair template id is not allowlisted")
    if envelope["template_sha256"] != policy.template_sha256:
        raise RuntimeAdapterValidationError("repair template hash is not allowlisted")
    nodes = envelope["nodes"]
    if not isinstance(nodes, Mapping) or dict(nodes) != dict(policy.node_allowlist):
        raise RuntimeAdapterValidationError("repair node allowlist mismatch")
    assets = envelope["assets"]
    if not isinstance(assets, Mapping) or dict(assets) != dict(policy.asset_allowlist):
        raise RuntimeAdapterValidationError("repair asset allowlist mismatch")
    workflow = envelope["workflow"]
    if not isinstance(workflow, Mapping) or _sha256(workflow) != policy.template_sha256:
        raise RuntimeAdapterValidationError("repair workflow bytes do not match frozen hash")


class RegionalHandRepairRuntimeAdapter:
    def __init__(
        self,
        *,
        evidence_store: RegionalHandRepairEvidenceStore,
        transport: RepairTransport,
        workflow_provider: Callable[[ExecutionLaunchAttempt], Mapping[str, Any]],
        policy: FrozenRepairWorkflowPolicy,
    ) -> None:
        if transport.endpoint != PILOT_ENDPOINT:
            raise RuntimeAdapterValidationError(
                f"only the canonical loopback ComfyUI endpoint is permitted: {PILOT_ENDPOINT}"
            )
        self._store = evidence_store
        self._transport = transport
        self._workflow_provider = workflow_provider
        self._policy = policy

    def _validate_lineage(
        self,
        binding: WorkerRuntimeBinding,
        launch_attempt: ExecutionLaunchAttempt,
        idempotency_key: str,
    ) -> None:
        if binding.adapter_kind != WorkerRuntimeAdapterKind.HTTP_WORKER_ADAPTER:
            raise RuntimeAdapterValidationError("repair pilot requires HTTP_WORKER_ADAPTER")
        if not binding.enabled or not binding.supports_idempotency:
            raise RuntimeAdapterValidationError("repair binding must be enabled and idempotent")
        if binding.worker_id != PILOT_WORKER_ID or binding.worker_version != PILOT_WORKER_VERSION:
            raise RuntimeAdapterValidationError("repair worker identity/version mismatch")
        if binding.worker_class != PILOT_WORKER_CLASS:
            raise RuntimeAdapterValidationError("repair worker class mismatch")
        if launch_attempt.operation != PILOT_OPERATION:
            raise RuntimeAdapterValidationError("repair operation mismatch")
        if PILOT_OPERATION not in binding.allowed_operations:
            raise RuntimeAdapterValidationError("repair operation is not allowed by binding")
        if idempotency_key != launch_attempt.idempotency_key:
            raise RuntimeAdapterValidationError("idempotency key override rejected")
        if launch_attempt.worker_id != binding.worker_id:
            raise RuntimeAdapterValidationError("launch worker does not match binding")
        if launch_attempt.worker_version != binding.worker_version:
            raise RuntimeAdapterValidationError("launch worker version does not match binding")
        if launch_attempt.runtime_binding_id != binding.runtime_binding_id:
            raise RuntimeAdapterValidationError("runtime binding identity mismatch")
        if launch_attempt.runtime_binding_hash != binding.artifact_hash:
            raise RuntimeAdapterValidationError("runtime binding hash mismatch")

    @staticmethod
    def _stored_result(run: RepairRun) -> RuntimeLaunchResult | None:
        if run.state in {"STARTED", "OUTPUT_CAPTURED", "VERIFIED"}:
            return RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.STARTED,
                runtime_run_id=run.runtime_run_id,
            )
        if run.state == "FAILED":
            detail = json.loads(run.result_json) if run.result_json else {}
            return RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.FAILED,
                error_code=detail.get("error_code", "REPAIR_FAILED"),
                error_summary=detail.get("error_summary"),
            )
        return None

    def _reconcile_uncertain(self, idempotency_key: str) -> RuntimeLaunchResult:
        lookup = self._transport.lookup(idempotency_key)
        if lookup.outcome == RuntimeLookupOutcome.FOUND_STARTED:
            self._store.transition(
                idempotency_key,
                "STARTED",
                runtime_run_id=lookup.runtime_run_id,
                result={"reconciled": True, "outcome": lookup.outcome.value},
            )
            return RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.STARTED,
                runtime_run_id=lookup.runtime_run_id,
            )
        if lookup.outcome in {
            RuntimeLookupOutcome.FOUND_FAILED,
            RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE,
        }:
            self._store.transition(
                idempotency_key,
                "FAILED",
                result={
                    "reconciled": True,
                    "outcome": lookup.outcome.value,
                    "error_code": lookup.error_code or "RECONCILED_NON_START",
                    "error_summary": lookup.error_summary,
                },
            )
            return RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.FAILED,
                error_code=lookup.error_code or "RECONCILED_NON_START",
                error_summary=lookup.error_summary,
            )
        return RuntimeLaunchResult(
            outcome=RuntimeLaunchOutcome.UNKNOWN,
            runtime_run_id=lookup.runtime_run_id,
            error_code=lookup.error_code or "RECONCILIATION_PENDING",
            error_summary=lookup.error_summary,
        )

    def launch(
        self,
        *,
        binding: WorkerRuntimeBinding,
        launch_attempt: ExecutionLaunchAttempt,
        idempotency_key: str,
    ) -> RuntimeLaunchResult:
        self._validate_lineage(binding, launch_attempt, idempotency_key)
        existing = self._store.get_by_key(idempotency_key)
        if existing is not None:
            stored = self._stored_result(existing)
            if stored is not None:
                return stored
            if existing.state in {"SUBMITTING", "SUBMISSION_UNKNOWN"}:
                return self._reconcile_uncertain(idempotency_key)
            if existing.state != "RECORDED":
                raise RuntimeAdapterConflictError(
                    f"unsupported persisted repair state: {existing.state}"
                )

        envelope = self._workflow_provider(launch_attempt)
        validate_repair_workflow_envelope(envelope, self._policy)
        if envelope["task_input_sha256"] != launch_attempt.input_hash:
            raise RuntimeAdapterValidationError("repair task input hash mismatch")
        self._store.record(
            launch_attempt_id=launch_attempt.launch_attempt_id,
            idempotency_key=idempotency_key,
            repair_execution_id=str(envelope["repair_execution_id"]),
            task_input_sha256=str(envelope["task_input_sha256"]),
            worker_id=binding.worker_id,
            worker_version=binding.worker_version,
            runtime_binding_id=binding.runtime_binding_id,
        )
        self._store.transition(idempotency_key, "SUBMITTING")
        try:
            runtime_run_id = self._transport.submit(envelope["workflow"], idempotency_key)
        except (TimeoutError, ConnectionError) as exc:
            self._store.transition(
                idempotency_key,
                "SUBMISSION_UNKNOWN",
                result={"error_code": "SUBMISSION_AMBIGUOUS", "error_summary": str(exc)},
            )
            return RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.UNKNOWN,
                error_code="SUBMISSION_AMBIGUOUS",
                error_summary=str(exc),
            )
        if not runtime_run_id:
            self._store.transition(
                idempotency_key,
                "SUBMISSION_UNKNOWN",
                result={"error_code": "EMPTY_RUNTIME_ACK"},
            )
            return RuntimeLaunchResult(
                outcome=RuntimeLaunchOutcome.UNKNOWN,
                error_code="EMPTY_RUNTIME_ACK",
            )
        self._store.transition(
            idempotency_key,
            "STARTED",
            runtime_run_id=runtime_run_id,
            result={"outcome": "STARTED", "runtime_run_id": runtime_run_id},
        )
        return RuntimeLaunchResult(
            outcome=RuntimeLaunchOutcome.STARTED,
            runtime_run_id=runtime_run_id,
        )

    def lookup(self, idempotency_key: str) -> RuntimeLookupResult:
        run = self._store.get_by_key(idempotency_key)
        if run is None:
            return RuntimeLookupResult(
                outcome=RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE
            )
        stored = self._stored_result(run)
        if stored is not None and stored.outcome == RuntimeLaunchOutcome.STARTED:
            return RuntimeLookupResult(
                outcome=RuntimeLookupOutcome.FOUND_STARTED,
                runtime_run_id=stored.runtime_run_id,
            )
        if stored is not None and stored.outcome == RuntimeLaunchOutcome.FAILED:
            return RuntimeLookupResult(
                outcome=RuntimeLookupOutcome.FOUND_FAILED,
                error_code=stored.error_code,
                error_summary=stored.error_summary,
            )
        return self._transport.lookup(idempotency_key)
