"""Scripted collaborator tests, not native containment qualification."""

import pytest

from tools.ea4e92s_containment_lifecycle import exercise_lifecycle


class FakeBackend:
    def __init__(self, admission=True, limits=True, cleanup=True, failure=None,
                 output=b"synthetic", handle=None):
        self.admission = admission
        self.limits = limits
        self.cleanup = cleanup
        self.failure = failure
        self.output = output
        self.handle = object() if handle is None else handle
        self.events = []

    def step(self, name, value, owned=None):
        self.events.append(name)
        if owned is not None:
            assert owned is self.handle
        if self.failure == name:
            raise RuntimeError("scripted failure")
        return value

    def validate_admission(self):
        return self.step("admit", self.admission)

    def create_suspended(self):
        return self.step("create", self.handle)

    def apply_and_verify_limits(self, owned):
        return self.step("limits", self.limits, owned)

    def resume_and_capture(self, owned):
        return self.step("capture", self.output, owned)

    def terminate_and_close(self, owned):
        return self.step("cleanup", self.cleanup, owned)


def test_order_and_unvalidated_output():
    backend = FakeBackend()
    result = exercise_lifecycle(backend)
    assert result.status == "CAPTURED_UNVALIDATED"
    assert result.output == b"synthetic"
    assert backend.events == ["admit", "create", "limits", "capture", "cleanup"]


@pytest.mark.parametrize("admission", [False, None, 1, "yes"])
def test_admission_denies_before_creation(admission):
    backend = FakeBackend(admission=admission)
    assert exercise_lifecycle(backend).status == "DENIED"
    assert backend.events == ["admit"]


def test_admission_exception():
    backend = FakeBackend(failure="admit")
    assert exercise_lifecycle(backend).status == "DENIED"
    assert backend.events == ["admit"]


def test_creation_failure_is_unknown_not_safe_retry():
    backend = FakeBackend(failure="create")
    assert exercise_lifecycle(backend).status == "UNKNOWN_CONTAINMENT_OUTCOME"
    assert backend.events == ["admit", "create"]


@pytest.mark.parametrize("limits", [False, None, 1])
def test_failed_limits_never_resume(limits):
    backend = FakeBackend(limits=limits)
    assert exercise_lifecycle(backend).status == "DENIED"
    assert backend.events == ["admit", "create", "limits", "cleanup"]


@pytest.mark.parametrize("failure", ["limits", "capture"])
def test_owned_cleanup_after_failure(failure):
    backend = FakeBackend(failure=failure)
    result = exercise_lifecycle(backend)
    assert result.status == "DENIED"
    assert result.output is None
    assert backend.events[-1] == "cleanup"


@pytest.mark.parametrize("cleanup", [False, None, 1])
def test_unknown_cleanup_discards_result(cleanup):
    backend = FakeBackend(cleanup=cleanup)
    result = exercise_lifecycle(backend)
    assert result.status == "UNKNOWN_CONTAINMENT_OUTCOME"
    assert result.output is None


def test_cleanup_exception():
    backend = FakeBackend(failure="cleanup")
    assert exercise_lifecycle(backend).status == "UNKNOWN_CONTAINMENT_OUTCOME"


@pytest.mark.parametrize("output", ["text", bytearray(b"text"), b"x" * (4 * 1024 * 1024 + 1)],
                         ids=["text", "mutable-bytes", "overflow"])
def test_invalid_capture_denied_and_cleaned(output):
    backend = FakeBackend(output=output)
    assert exercise_lifecycle(backend).status == "DENIED"
    assert backend.events[-1] == "cleanup"
