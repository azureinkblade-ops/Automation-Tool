"""Injected collaborator only; no native process, Docker, or Buildx."""

from dataclasses import replace

import pytest

from tools.ea4e92s_suspended_process import (
    SuspendedCreationResult, SuspendedProcessDenied, UnknownSuspendedProcess,
)
from tools.ea4e92s_windows_attributes import WindowsAttributeApi
from tools.ea4e92wq_buildx_job_attributes import prepare_buildx_job_attributes
from tools.ea4e92wr_buildx_suspended_process import create_owned_buildx_suspended_process


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class FakeKernel:
    def __init__(self):
        self.InitializeProcThreadAttributeList = Function(self.initialize)
        self.UpdateProcThreadAttribute = Function(lambda *args: 1)
        self.DeleteProcThreadAttributeList = Function(lambda *args: None)

    def initialize(self, buffer, count, flags, size):
        assert count == 1 and flags == 0
        size._obj.value = 128
        return 0 if buffer is None else 1


class FakeProcessApi:
    def __init__(self, result=None, create_error=None, terminate=True):
        self.result = result if result is not None else SuspendedCreationResult(
            101, 102, 201, 202, True, True, False)
        self.create_error = create_error
        self.terminate_result = terminate
        self.events = []

    def create_suspended(self, attribute_buffer):
        self.events.append(("create", attribute_buffer))
        if self.create_error:
            raise self.create_error
        return self.result

    def terminate(self, process_handle):
        self.events.append(("terminate", process_handle))
        return self.terminate_result

    def close_thread(self, thread_handle):
        self.events.append(("close_thread", thread_handle))
        return True

    def close_process(self, process_handle):
        self.events.append(("close_process", process_handle))
        return True


def prepared():
    kernel = FakeKernel()
    adapter = WindowsAttributeApi(kernel, lambda: 122, job_only=True)
    return prepare_buildx_job_attributes(adapter, 71)


def test_exact_job_only_owner_is_borrowed_without_resume():
    attributes = prepared()
    api = FakeProcessApi()
    owned = create_owned_buildx_suspended_process(api, attributes)
    assert owned.creation_owner is attributes
    assert api.events == [("create", attributes.handle.buffer)]
    owned.close()
    assert [event[0] for event in api.events] == [
        "create", "terminate", "close_thread", "close_process"]
    attributes.close()


@pytest.mark.parametrize("change", [
    "state", "profile", "closed", "failed", "keys", "values", "keepalive",
])
def test_invalid_owner_denied_before_creation(change):
    attributes = prepared()
    if change == "state":
        attributes.state = "unknown"
    elif change == "profile":
        attributes.api.job_only = False
    elif change == "closed":
        attributes.handle.closed = True
    elif change == "failed":
        attributes.handle.failed = True
    elif change == "keys":
        attributes.handle.keys.append("SECURITY_CAPABILITIES")
    elif change == "values":
        attributes.handle.values.clear()
    else:
        attributes.keepalive = ()
    api = FakeProcessApi()
    with pytest.raises(ValueError):
        create_owned_buildx_suspended_process(api, attributes)
    assert api.events == []


def test_create_exception_is_unknown_and_not_retried():
    attributes = prepared()
    api = FakeProcessApi(create_error=OSError("injected ambiguity"))
    with pytest.raises(UnknownSuspendedProcess, match="reconciliation"):
        create_owned_buildx_suspended_process(api, attributes)
    assert len(api.events) == 1


@pytest.mark.parametrize("change", [
    {"process_handle": 0}, {"thread_handle": True}, {"thread_handle": 101},
])
def test_invalid_handle_is_unknown(change):
    attributes = prepared()
    result = replace(FakeProcessApi().result, **change)
    api = FakeProcessApi(result=result)
    with pytest.raises(UnknownSuspendedProcess, match="handle ownership"):
        create_owned_buildx_suspended_process(api, attributes)
    assert [event[0] for event in api.events] == ["create"]


@pytest.mark.parametrize("change", [
    {"process_id": 0}, {"thread_id": True}, {"suspended": False},
    {"job_bound_at_creation": 1}, {"appcontainer_bound_at_creation": True},
])
def test_unproven_identity_or_predicate_is_terminated(change):
    attributes = prepared()
    api = FakeProcessApi(result=replace(FakeProcessApi().result, **change))
    with pytest.raises(SuspendedProcessDenied):
        create_owned_buildx_suspended_process(api, attributes)
    assert [event[0] for event in api.events] == [
        "create", "terminate", "close_thread", "close_process"]


def test_uncertain_cleanup_retains_process_and_attribute_owner():
    attributes = prepared()
    api = FakeProcessApi(result=replace(FakeProcessApi().result, suspended=False),
                         terminate=False)
    with pytest.raises(UnknownSuspendedProcess) as caught:
        create_owned_buildx_suspended_process(api, attributes)
    assert caught.value.owned.creation_owner is attributes
    assert caught.value.owned.state == "unknown"
    assert [event[0] for event in api.events] == ["create", "terminate"]
