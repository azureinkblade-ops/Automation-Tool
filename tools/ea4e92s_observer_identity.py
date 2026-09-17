"""Value-only identity binding for a future NQ-12 resource watcher."""

from dataclasses import dataclass
import re
import uuid


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ObserverIdentityDenied(ValueError):
    """The proposed watcher binding is not exact or is not canonical."""


@dataclass(frozen=True)
class ObserverResourceBinding:
    observer_instance_id: str
    job_token_sha256: str
    process_token_sha256: str
    thread_token_sha256: str
    process_id: int
    thread_id: int
    process_creation_time_100ns: int
    thread_creation_time_100ns: int
    binding_monotonic_ns: int


def _canonical_uuid(value):
    if type(value) is not str:
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _sha256(value):
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _positive_int(value, maximum=None):
    return (type(value) is int and value > 0
            and (maximum is None or value <= maximum))


def validate_observer_resource_binding(
        binding, *, observer_instance_id, process_id, thread_id):
    """Return one exact binding only when every durable identity agrees.

    Tokens represent handles already retained by a separate watcher. They are
    opaque identities, never serialized native handle values. This function
    performs no lookup, discovery, process inspection or retry.
    """
    if type(binding) is not ObserverResourceBinding:
        raise ObserverIdentityDenied("exact observer resource binding required")
    if not _canonical_uuid(observer_instance_id):
        raise ObserverIdentityDenied("expected observer identity malformed")
    if binding.observer_instance_id != observer_instance_id:
        raise ObserverIdentityDenied("observer instance identity mismatch")
    tokens = (
        binding.job_token_sha256,
        binding.process_token_sha256,
        binding.thread_token_sha256,
    )
    if any(not _sha256(value) for value in tokens) or len(set(tokens)) != 3:
        raise ObserverIdentityDenied("opaque resource tokens malformed")
    if not _positive_int(process_id, 0xFFFFFFFF):
        raise ObserverIdentityDenied("expected process identity malformed")
    if not _positive_int(thread_id, 0xFFFFFFFF):
        raise ObserverIdentityDenied("expected thread identity malformed")
    if binding.process_id != process_id or binding.thread_id != thread_id:
        raise ObserverIdentityDenied("process or thread identity mismatch")
    if not _positive_int(binding.process_creation_time_100ns):
        raise ObserverIdentityDenied("process creation identity malformed")
    if not _positive_int(binding.thread_creation_time_100ns):
        raise ObserverIdentityDenied("thread creation identity malformed")
    if not _positive_int(binding.binding_monotonic_ns):
        raise ObserverIdentityDenied("binding time malformed")
    return binding
