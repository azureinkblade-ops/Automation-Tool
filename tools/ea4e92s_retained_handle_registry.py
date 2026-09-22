"""Pure in-memory retained-handle ownership for future EA-4E.92S NQ-12."""

from dataclasses import dataclass
import sys
import threading
import uuid

from tools.ea4e92s_observer_identity import (
    ObserverIdentityDenied,
    ObserverResourceBinding,
    validate_observer_resource_binding,
)


CLEANUP_ORDER = (
    "TERMINATE_JOB", "CLOSE_THREAD", "CLOSE_PROCESS", "CLOSE_JOB")


class RetainedHandleRegistryDenied(RuntimeError):
    """Exact watcher-owned resource authority is absent or conflicted."""


@dataclass(frozen=True)
class RetainedHandleResolution:
    binding: ObserverResourceBinding
    job_handle: int
    process_handle: int
    thread_handle: int


@dataclass(frozen=True)
class CleanupTombstone:
    binding: ObserverResourceBinding
    monotonic_observed_ns: int
    cleanup_order: tuple[str, ...]
    active_process_count: int
    process_present: bool
    thread_present: bool
    owned_handles_closed: bool


@dataclass
class _RegistryEntry:
    binding: ObserverResourceBinding
    job_handle: int | None
    process_handle: int | None
    thread_handle: int | None
    tombstone: CleanupTombstone | None = None


def _canonical_uuid(value):
    if type(value) is not str:
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _valid_handle(value):
    maximum = (2 * sys.maxsize) + 1
    return type(value) is int and 0 < value <= maximum


def _tokens(binding):
    return (
        binding.job_token_sha256,
        binding.process_token_sha256,
        binding.thread_token_sha256,
    )


class RetainedHandleRegistry:
    """Serialize exact in-memory handle ownership without native operations."""

    def __init__(self, *, observer_instance_id):
        if not _canonical_uuid(observer_instance_id):
            raise RetainedHandleRegistryDenied("observer instance identity malformed")
        self.observer_instance_id = observer_instance_id
        self._entries = {}
        self._token_owners = {}
        self._lock = threading.Lock()

    def _validate(self, binding, *, process_id, thread_id):
        try:
            return validate_observer_resource_binding(
                binding,
                observer_instance_id=self.observer_instance_id,
                process_id=process_id,
                thread_id=thread_id,
            )
        except ObserverIdentityDenied as error:
            raise RetainedHandleRegistryDenied(
                "observer resource binding denied") from error

    def register(
            self, binding, *, process_id, thread_id,
            job_handle, process_handle, thread_handle):
        binding = self._validate(
            binding, process_id=process_id, thread_id=thread_id)
        handles = (job_handle, process_handle, thread_handle)
        if any(not _valid_handle(value) for value in handles):
            raise RetainedHandleRegistryDenied("retained handle malformed")
        if len(set(handles)) != 3:
            raise RetainedHandleRegistryDenied("retained handles are not distinct")
        key = binding.job_token_sha256
        tokens = _tokens(binding)
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                if existing.tombstone is not None:
                    raise RetainedHandleRegistryDenied(
                        "cleaned resource registration cannot replay")
                if (existing.binding != binding or (
                        existing.job_handle, existing.process_handle,
                        existing.thread_handle) != handles):
                    raise RetainedHandleRegistryDenied(
                        "retained resource registration conflicts")
                return RetainedHandleResolution(binding, *handles)
            if any(token in self._token_owners for token in tokens):
                raise RetainedHandleRegistryDenied("opaque resource token conflicts")
            entry = _RegistryEntry(binding, *handles)
            self._entries[key] = entry
            for token in tokens:
                self._token_owners[token] = key
            return RetainedHandleResolution(binding, *handles)

    def resolve(self, binding, *, process_id, thread_id):
        binding = self._validate(
            binding, process_id=process_id, thread_id=thread_id)
        key = binding.job_token_sha256
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or any(
                    self._token_owners.get(token) != key
                    for token in _tokens(binding)):
                raise RetainedHandleRegistryDenied("retained resource is unavailable")
            if entry.binding != binding:
                raise RetainedHandleRegistryDenied("retained resource binding conflicts")
            if entry.tombstone is not None:
                raise RetainedHandleRegistryDenied("retained handles are cleaned")
            handles = (
                entry.job_handle, entry.process_handle, entry.thread_handle)
            if any(not _valid_handle(value) for value in handles):
                raise RetainedHandleRegistryDenied("retained handle state is unknown")
            return RetainedHandleResolution(binding, *handles)

    def seal_cleanup(self, binding, tombstone, *, process_id, thread_id):
        binding = self._validate(
            binding, process_id=process_id, thread_id=thread_id)
        if type(tombstone) is not CleanupTombstone:
            raise RetainedHandleRegistryDenied("exact cleanup tombstone required")
        if tombstone.binding != binding:
            raise RetainedHandleRegistryDenied("cleanup binding conflicts")
        if (type(tombstone.monotonic_observed_ns) is not int
                or tombstone.monotonic_observed_ns
                < binding.binding_monotonic_ns):
            raise RetainedHandleRegistryDenied("cleanup observation time malformed")
        if tombstone.cleanup_order != CLEANUP_ORDER:
            raise RetainedHandleRegistryDenied("cleanup order conflicts")
        if (type(tombstone.active_process_count) is not int
                or tombstone.active_process_count != 0):
            raise RetainedHandleRegistryDenied("cleaned process count required")
        predicates = (
            tombstone.process_present,
            tombstone.thread_present,
            tombstone.owned_handles_closed,
        )
        if any(type(value) is not bool for value in predicates):
            raise RetainedHandleRegistryDenied("cleanup predicate malformed")
        if predicates != (False, False, True):
            raise RetainedHandleRegistryDenied("cleanup is not confirmed")
        key = binding.job_token_sha256
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.binding != binding:
                raise RetainedHandleRegistryDenied("retained resource is unavailable")
            if entry.tombstone is not None:
                if entry.tombstone == tombstone:
                    return entry.tombstone
                raise RetainedHandleRegistryDenied("cleanup replay conflicts")
            entry.job_handle = None
            entry.process_handle = None
            entry.thread_handle = None
            entry.tombstone = tombstone
            return tombstone

    def read_tombstone(self, binding, *, process_id, thread_id):
        binding = self._validate(
            binding, process_id=process_id, thread_id=thread_id)
        key = binding.job_token_sha256
        with self._lock:
            entry = self._entries.get(key)
            if (entry is None or entry.binding != binding
                    or entry.tombstone is None):
                raise RetainedHandleRegistryDenied("cleanup tombstone is unavailable")
            return entry.tombstone
