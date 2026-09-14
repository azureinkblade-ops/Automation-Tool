"""Test-owned containment lifecycle; no native backend or launch authority."""

from dataclasses import dataclass
from typing import Protocol


class ContainmentBackend(Protocol):
    """Trusted injected boundary, not evidence supplied by the worker.

    A future backend must enforce deadlines and stream caps during capture.
    The final length check here cannot replace OS or incremental enforcement.
    """

    def validate_admission(self) -> bool: ...
    def create_suspended(self) -> object: ...
    def apply_and_verify_limits(self, owned: object) -> bool: ...
    def resume_and_capture(self, owned: object) -> bytes: ...
    def terminate_and_close(self, owned: object) -> bool: ...


@dataclass(frozen=True)
class LifecycleResult:
    status: str
    output: bytes | None = None


def exercise_lifecycle(backend: ContainmentBackend) -> LifecycleResult:
    """Exercise injected collaborators, never qualify OS enforcement from output.

    A failed creation must clean up inside the backend before raising, since the
    caller has no owned handle. The caller must stop subsequent requests after
    UNKNOWN_CONTAINMENT_OUTCOME. Native implementations are not supplied here.
    """
    try:
        if backend.validate_admission() is not True:
            return LifecycleResult("DENIED")
    except Exception:
        return LifecycleResult("DENIED")

    try:
        owned = backend.create_suspended()
    except Exception:
        return LifecycleResult("UNKNOWN_CONTAINMENT_OUTCOME")
    if owned is None:
        return LifecycleResult("UNKNOWN_CONTAINMENT_OUTCOME")

    result = LifecycleResult("DENIED")
    try:
        if backend.apply_and_verify_limits(owned) is True:
            output = backend.resume_and_capture(owned)
            if type(output) is bytes and len(output) <= 4 * 1024 * 1024:
                result = LifecycleResult("CAPTURED_UNVALIDATED", output)
    except Exception:
        result = LifecycleResult("DENIED")
    finally:
        try:
            cleaned = backend.terminate_and_close(owned)
        except Exception:
            cleaned = False
        if cleaned is not True:
            result = LifecycleResult("UNKNOWN_CONTAINMENT_OUTCOME")
    return result
