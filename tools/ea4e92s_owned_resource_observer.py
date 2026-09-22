"""Value-only NQ-12 owned-resource observation; no native implementation."""

import ctypes
from dataclasses import dataclass
from typing import Protocol

from tools.ea4e92s_observer_identity import (
    ObserverIdentityDenied,
    ObserverResourceBinding,
    validate_observer_resource_binding,
)
from tools.ea4e92s_probe_evidence_store import BrokerDeathObservation


CLEANUP_ORDER = (
    "TERMINATE_JOB", "CLOSE_THREAD", "CLOSE_PROCESS", "CLOSE_JOB")


class OwnedResourceObservationUnknown(RuntimeError):
    """The provider did not return exact, trustworthy value evidence."""


@dataclass(frozen=True)
class OwnedResourceSnapshot:
    job_id: int
    process_id: int
    thread_id: int
    monotonic_observed_ns: int
    cleanup_order: tuple[str, ...]
    active_process_count: int
    process_present: bool
    thread_present: bool
    owned_handles_closed: bool


class OwnedResourceSnapshotProvider(Protocol):
    def observe_owned_resources(
            self, *, observer_binding: ObserverResourceBinding,
            job_id: int, process_id: int,
            thread_id: int) -> OwnedResourceSnapshot: ...


def _valid_identity(value, maximum):
    return type(value) is int and 0 < value <= maximum


class ExactOwnedResourceObserver:
    """Validate one injected snapshot and project canonical durable evidence.

    The provider owns any future native inspection. This adapter performs one
    provider call, has no retry or fallback path, and never discovers, mutates,
    terminates or closes a resource itself.
    """

    def __init__(self, provider, *, observer_instance_id):
        self.provider = provider
        self.observer_instance_id = observer_instance_id

    def observe_exact(
            self, *, observer_binding, job_id, process_id, thread_id):
        pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
        if not _valid_identity(job_id, pointer_max):
            raise OwnedResourceObservationUnknown("job identity malformed")
        if not _valid_identity(process_id, 0xFFFFFFFF):
            raise OwnedResourceObservationUnknown("process identity malformed")
        if not _valid_identity(thread_id, 0xFFFFFFFF):
            raise OwnedResourceObservationUnknown("thread identity malformed")
        try:
            validated_binding = validate_observer_resource_binding(
                observer_binding,
                observer_instance_id=self.observer_instance_id,
                process_id=process_id,
                thread_id=thread_id,
            )
        except ObserverIdentityDenied as error:
            raise OwnedResourceObservationUnknown(
                "observer resource binding malformed") from error

        operation = getattr(self.provider, "observe_owned_resources", None)
        if not callable(operation):
            raise OwnedResourceObservationUnknown("snapshot provider unavailable")
        try:
            snapshot = operation(
                observer_binding=validated_binding,
                job_id=job_id, process_id=process_id, thread_id=thread_id)
        except BaseException as error:
            raise OwnedResourceObservationUnknown(
                "owned-resource snapshot failed") from error

        if type(snapshot) is not OwnedResourceSnapshot:
            raise OwnedResourceObservationUnknown("snapshot type malformed")
        if (snapshot.job_id, snapshot.process_id, snapshot.thread_id) != (
                job_id, process_id, thread_id):
            raise OwnedResourceObservationUnknown("snapshot identity mismatch")
        if (type(snapshot.monotonic_observed_ns) is not int
                or snapshot.monotonic_observed_ns <= 0):
            raise OwnedResourceObservationUnknown("snapshot time malformed")
        if snapshot.cleanup_order != CLEANUP_ORDER:
            raise OwnedResourceObservationUnknown("cleanup order malformed")
        if (type(snapshot.active_process_count) is not int
                or snapshot.active_process_count < 0):
            raise OwnedResourceObservationUnknown("process count malformed")
        predicates = (
            snapshot.process_present,
            snapshot.thread_present,
            snapshot.owned_handles_closed,
        )
        if any(type(value) is not bool for value in predicates):
            raise OwnedResourceObservationUnknown("snapshot predicate malformed")

        cleanup_confirmed = (
            snapshot.active_process_count == 0
            and snapshot.process_present is False
            and snapshot.thread_present is False
            and snapshot.owned_handles_closed is True
        )
        return BrokerDeathObservation(
            observed_job_id=job_id,
            observed_process_id=process_id,
            observed_thread_id=thread_id,
            monotonic_observed_ns=snapshot.monotonic_observed_ns,
            cleanup_order=snapshot.cleanup_order,
            cleanup_confirmed=cleanup_confirmed,
            surviving_owned_processes=snapshot.active_process_count,
        )
