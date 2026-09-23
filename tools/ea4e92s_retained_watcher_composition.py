"""Explicit non-live composition of one retained-resource watcher."""

from dataclasses import dataclass

from tools.ea4e92s_owned_resource_observer import ExactOwnedResourceObserver
from tools.ea4e92s_retained_cleanup_owner import RetainedCleanupOwner
from tools.ea4e92s_retained_handle_registry import RetainedHandleRegistry
from tools.ea4e92s_retained_snapshot_provider import RetainedSnapshotProvider


@dataclass(frozen=True)
class RetainedWatcherComposition:
    registry: RetainedHandleRegistry
    provider: RetainedSnapshotProvider
    observer: ExactOwnedResourceObserver
    cleanup_owner: RetainedCleanupOwner


def compose_retained_watcher(registry, resource_api, *, monotonic_ns):
    """Share one exact registry and injected API; never acquire a native handle."""
    if type(registry) is not RetainedHandleRegistry:
        raise ValueError("exact retained registry required")
    operations = (
        "query_job", "query_process", "query_thread", "terminate_job",
        "close_thread", "close_process", "close_job")
    if not callable(monotonic_ns) or any(
            not callable(getattr(resource_api, name, None)) for name in operations):
        raise ValueError("complete injected resource API required")

    provider = RetainedSnapshotProvider(
        registry, query_job=resource_api.query_job,
        query_process=resource_api.query_process,
        query_thread=resource_api.query_thread, monotonic_ns=monotonic_ns)
    observer = ExactOwnedResourceObserver(
        provider, observer_instance_id=registry.observer_instance_id)
    cleanup_owner = RetainedCleanupOwner(
        registry, provider, terminate_job=resource_api.terminate_job,
        close_thread=resource_api.close_thread,
        close_process=resource_api.close_process,
        close_job=resource_api.close_job, monotonic_ns=monotonic_ns)
    return RetainedWatcherComposition(
        registry, provider, observer, cleanup_owner)
