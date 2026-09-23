"""One-shot watcher-owned cleanup using injected resource operations only."""

from tools.ea4e92s_retained_handle_registry import (
    CLEANUP_ORDER,
    CleanupTombstone,
)


class RetainedCleanupUnknown(RuntimeError):
    """The exact resource cleanup outcome cannot be confirmed."""


class RetainedCleanupOwner:
    def __init__(self, registry, snapshot_provider, *, terminate_job,
                 close_thread, close_process, close_job, monotonic_ns):
        self.registry = registry
        self.snapshot_provider = snapshot_provider
        self.terminate_job = terminate_job
        self.close_thread = close_thread
        self.close_process = close_process
        self.close_job = close_job
        self.monotonic_ns = monotonic_ns

    def cleanup(self, *, observer_binding, job_id, process_id, thread_id):
        if (type(job_id) is not int or job_id <= 0
                or type(process_id) is not int or process_id <= 0
                or type(thread_id) is not int or thread_id <= 0):
            raise RetainedCleanupUnknown("resource identity malformed")

        def execute(handles):
            query = self.snapshot_provider.query_retained
            arguments = dict(
                observer_binding=observer_binding, job_id=job_id,
                process_id=process_id, thread_id=thread_id)
            query(handles, **arguments)
            self._require_success(self.terminate_job, handles.job_handle)
            final = query(handles, **arguments)
            if (final.active_process_count != 0 or final.process_present
                    or final.thread_present):
                raise RetainedCleanupUnknown("owned resources still present")
            self._require_success(self.close_thread, handles.thread_handle)
            self._require_success(self.close_process, handles.process_handle)
            self._require_success(self.close_job, handles.job_handle)
            observed_ns = self.monotonic_ns()
            if (type(observed_ns) is not int
                    or observed_ns < final.monotonic_observed_ns):
                raise RetainedCleanupUnknown("cleanup time malformed")
            return CleanupTombstone(
                observer_binding, observed_ns, CLEANUP_ORDER,
                0, False, False, True)

        try:
            return self.registry.run_cleanup(
                observer_binding, process_id=process_id, thread_id=thread_id,
                execute=execute)
        except BaseException as error:
            raise RetainedCleanupUnknown("owned-resource cleanup unknown") from error

    @staticmethod
    def _require_success(operation, handle):
        if operation(handle) is not True:
            raise RetainedCleanupUnknown("owned-resource operation unconfirmed")
