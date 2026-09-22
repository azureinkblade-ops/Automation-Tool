"""One-shot, non-live reconciliation orchestration for EA-4E.92S NQ-12."""

from dataclasses import dataclass
from typing import Protocol

from tools.ea4e92s_observer_identity import ObserverResourceBinding
from tools.ea4e92s_probe_evidence_store import (
    BrokerDeathObservation,
    ProbeEvidenceStoreError,
    ProbeEvidenceStore,
)


class ReconciliationControllerDenied(RuntimeError):
    """The durable record is not eligible for NQ-12 reconciliation."""


class ReconciliationObservationUnknown(RuntimeError):
    """The observer did not produce exact value evidence."""


class OwnedResourceObserver(Protocol):
    def observe_exact(self, *, observer_binding: ObserverResourceBinding,
                      job_id: int, process_id: int,
                      thread_id: int) -> BrokerDeathObservation: ...


@dataclass(frozen=True)
class ReconciliationControllerResult:
    request_id: str
    state: str
    reconciliation_count: int
    observer_called: bool
    replayed: bool


def reconcile_broker_death(
        store, request_id, observer, *, observer_instance_id):
    """Request one exact observation and durably project it.

    The injected observer owns any future native inspection. This controller
    cannot discover or act on resources and never retries an observer call.
    """
    if type(store) is not ProbeEvidenceStore:
        raise ReconciliationControllerDenied("exact probe evidence store required")
    if type(request_id) is not str or not request_id or "\0" in request_id:
        raise ReconciliationControllerDenied("request identity malformed")

    record = store.get(request_id)
    if record.contract.probe_id != "NQ-12":
        raise ReconciliationControllerDenied("only NQ-12 broker death is eligible")
    if record.state == "RECONCILED_CLEAN":
        return ReconciliationControllerResult(
            request_id, record.state, record.reconciliation_count, False, True)
    if record.state != "UNKNOWN" or record.start is None:
        raise ReconciliationControllerDenied(
            "durable unknown owned-resource evidence required")
    if not callable(getattr(observer, "observe_exact", None)):
        raise ReconciliationObservationUnknown("exact observer boundary unavailable")
    try:
        observer_binding = store.require_native_observer_binding(
            request_id, observer_instance_id=observer_instance_id)
    except ProbeEvidenceStoreError as error:
        raise ReconciliationControllerDenied(
            "durable observer binding is unavailable") from error

    try:
        observation = observer.observe_exact(
            observer_binding=observer_binding,
            job_id=record.start.job_id,
            process_id=record.start.process_id,
            thread_id=record.start.thread_id,
        )
    except BaseException as error:
        raise ReconciliationObservationUnknown(
            "owned-resource observation failed; durable unknown remains") from error
    if type(observation) is not BrokerDeathObservation:
        raise ReconciliationObservationUnknown(
            "owned-resource observation malformed; durable unknown remains")

    updated = store.reconcile_unknown(request_id, observation)
    return ReconciliationControllerResult(
        request_id, updated.state, updated.reconciliation_count, True, False)
