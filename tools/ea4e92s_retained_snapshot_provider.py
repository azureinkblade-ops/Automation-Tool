"""Read-only NQ-12 snapshot provider with injected resource queries."""

from dataclasses import dataclass

from tools.ea4e92s_owned_resource_observer import (
    CLEANUP_ORDER,
    OwnedResourceObservationUnknown,
    OwnedResourceSnapshot,
)
from tools.ea4e92s_retained_handle_registry import (
    RetainedHandleRegistryDenied,
)


@dataclass(frozen=True)
class JobQuery:
    active_process_count: int


@dataclass(frozen=True)
class ProcessQuery:
    process_id: int
    creation_time_100ns: int
    present: bool


@dataclass(frozen=True)
class ThreadQuery:
    thread_id: int
    creation_time_100ns: int
    present: bool


class RetainedSnapshotProvider:
    """Query exact watcher-owned handles once under the registry lock."""

    def __init__(self, registry, *, query_job, query_process, query_thread,
                 monotonic_ns):
        self.registry = registry
        self.query_job = query_job
        self.query_process = query_process
        self.query_thread = query_thread
        self.monotonic_ns = monotonic_ns

    def observe_owned_resources(
            self, *, observer_binding, job_id, process_id, thread_id):
        if (type(job_id) is not int or job_id <= 0
                or type(process_id) is not int or process_id <= 0
                or type(thread_id) is not int or thread_id <= 0):
            raise OwnedResourceObservationUnknown("resource identity malformed")
        try:
            tombstone = self.registry.read_tombstone(
                observer_binding, process_id=process_id, thread_id=thread_id)
        except RetainedHandleRegistryDenied:
            tombstone = None
        if tombstone is not None:
            return OwnedResourceSnapshot(
                job_id, process_id, thread_id,
                tombstone.monotonic_observed_ns, tombstone.cleanup_order,
                tombstone.active_process_count, tombstone.process_present,
                tombstone.thread_present, tombstone.owned_handles_closed)

        try:
            return self.registry.with_retained(
                observer_binding, process_id=process_id, thread_id=thread_id,
                observe=lambda handles: self.query_retained(
                    handles, observer_binding=observer_binding, job_id=job_id,
                    process_id=process_id, thread_id=thread_id))
        except OwnedResourceObservationUnknown:
            raise
        except BaseException as error:
            raise OwnedResourceObservationUnknown(
                "retained resource query failed") from error

    def query_retained(
            self, handles, *, observer_binding, job_id, process_id, thread_id):
            job = self.query_job(handles.job_handle)
            if (type(job) is not JobQuery
                    or type(job.active_process_count) is not int
                    or not 0 <= job.active_process_count <= 0xFFFFFFFF):
                raise OwnedResourceObservationUnknown("job query malformed")
            process = self.query_process(handles.process_handle)
            if (type(process) is not ProcessQuery
                    or type(process.process_id) is not int
                    or process.process_id != process_id
                    or type(process.creation_time_100ns) is not int
                    or process.creation_time_100ns
                    != observer_binding.process_creation_time_100ns
                    or type(process.present) is not bool):
                raise OwnedResourceObservationUnknown("process identity drift")
            thread = self.query_thread(handles.thread_handle)
            if (type(thread) is not ThreadQuery
                    or type(thread.thread_id) is not int
                    or thread.thread_id != thread_id
                    or type(thread.creation_time_100ns) is not int
                    or thread.creation_time_100ns
                    != observer_binding.thread_creation_time_100ns
                    or type(thread.present) is not bool):
                raise OwnedResourceObservationUnknown("thread identity drift")
            if (job.active_process_count == 0 and process.present) or (
                    thread.present and not process.present):
                raise OwnedResourceObservationUnknown("resource state conflicts")
            observed_ns = self.monotonic_ns()
            if (type(observed_ns) is not int
                    or observed_ns < observer_binding.binding_monotonic_ns):
                raise OwnedResourceObservationUnknown("observation time malformed")
            return OwnedResourceSnapshot(
                job_id, process_id, thread_id, observed_ns, CLEANUP_ORDER,
                job.active_process_count, process.present, thread.present,
                False)
