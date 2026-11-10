"""Injected lifecycle tests only; no native job or process is used."""

from dataclasses import replace

import pytest

from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess, SuspendedCreationResult,
)
from tools.ea4e92s_windows_attributes import WindowsAttributeApi
from tools.ea4e92wq_buildx_job_attributes import prepare_buildx_job_attributes
from tools.ea4e92wt_buildx_startupinfo_abi import prepare_buildx_startup_info_ex
from tools.ea4e92wv_buildx_creation_owner import (
    UnknownBuildxOwnerCleanup, prepare_buildx_creation_owner,
)


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class FakeKernel:
    def __init__(self, events):
        self.events = events
        self.InitializeProcThreadAttributeList = Function(self.initialize)
        self.UpdateProcThreadAttribute = Function(lambda *args: 1)
        self.DeleteProcThreadAttributeList = Function(self.delete)

    def initialize(self, buffer, count, flags, size):
        assert count == 1 and flags == 0
        size._obj.value = 128
        return 0 if buffer is None else 1

    def delete(self, buffer):
        self.events.append("attributes")


class FakeJobApi:
    def __init__(self, events, result=True):
        self.events = events
        self.result = result

    def close(self, handle):
        self.events.append(("job", handle))
        return self.result


class FakeProcessApi:
    def __init__(self, events, terminate=True):
        self.events = events
        self.terminate_result = terminate

    def terminate(self, handle):
        self.events.append("terminate")
        return self.terminate_result

    def close_thread(self, handle):
        self.events.append("thread")
        return True

    def close_process(self, handle):
        self.events.append("process")
        return True


def owner(events=None, *, job_result=True):
    events = [] if events is None else events
    kernel = FakeKernel(events)
    attributes = prepare_buildx_job_attributes(
        WindowsAttributeApi(kernel, lambda: 122, job_only=True), 71)
    startup = prepare_buildx_startup_info_ex(attributes)
    return prepare_buildx_creation_owner(
        FakeJobApi(events, job_result), 71, attributes, startup), events


def process(owner, events, *, terminate=True, result=None):
    result = result or SuspendedCreationResult(101, 102, 201, 202, True, True, False)
    return OwnedSuspendedProcess(FakeProcessApi(events, terminate), result,
                                 owner.attributes)


def test_unlaunched_owner_closes_attributes_before_job():
    owned, events = owner()
    owned.close()
    owned.close()
    assert owned.state == "closed"
    assert events == ["attributes", ("job", 71)]


def test_attached_process_closes_before_attributes_and_job():
    owned, events = owner()
    child = process(owned, events)
    owned.attach(child)
    owned.close()
    assert child.state == owned.state == "closed"
    assert events == ["terminate", "thread", "process", "attributes", ("job", 71)]


@pytest.mark.parametrize("change", ["job", "state", "startup", "pointer"])
def test_unmatched_creation_resources_denied(change):
    owned, events = owner()
    if change == "job":
        owned.job_handle = 72
    elif change == "state":
        owned.attributes.state = "unknown"
    elif change == "startup":
        owned.startup = replace(owned.startup, attributes=object())
    else:
        owned.startup.value.lpAttributeList = 0
    with pytest.raises(ValueError):
        prepare_buildx_creation_owner(
            owned.job_api, owned.job_handle, owned.attributes, owned.startup)
    assert events == []


def test_second_or_unowned_process_attachment_denied():
    owned, events = owner()
    child = process(owned, events)
    owned.attach(child)
    with pytest.raises(ValueError):
        owned.attach(child)
    assert owned.process is child


@pytest.mark.parametrize("change", ["unbound", "appcontainer", "other_owner"])
def test_unproven_process_attachment_denied(change):
    owned, events = owner()
    child = process(owned, events)
    if change == "unbound":
        child.result = replace(child.result, job_bound_at_creation=False)
    elif change == "appcontainer":
        child.result = replace(child.result, appcontainer_bound_at_creation=True)
    else:
        child.creation_owner = object()
    with pytest.raises(ValueError):
        owned.attach(child)
    assert owned.process is None and events == []


def test_uncertain_process_cleanup_retains_all_owners():
    owned, events = owner()
    owned.attach(process(owned, events, terminate=False))
    with pytest.raises(UnknownBuildxOwnerCleanup) as caught:
        owned.close()
    assert caught.value.owner is owned and owned.state == "unknown"
    assert events == ["terminate"]
    with pytest.raises(UnknownBuildxOwnerCleanup):
        owned.close()
    assert events == ["terminate"]


def test_uncertain_job_cleanup_retains_owner():
    owned, events = owner(job_result=False)
    with pytest.raises(UnknownBuildxOwnerCleanup) as caught:
        owned.close()
    assert caught.value.owner is owned and owned.state == "unknown"
    assert events == ["attributes", ("job", 71)]


def test_uncertain_attribute_cleanup_does_not_close_job():
    owned, events = owner()

    def fail_delete(buffer):
        raise OSError("injected deletion ambiguity")

    owned.attributes.api.dll.DeleteProcThreadAttributeList.implementation = fail_delete
    with pytest.raises(UnknownBuildxOwnerCleanup) as caught:
        owned.close()
    assert caught.value.owner is owned and owned.state == "unknown"
    assert owned.attributes.state == "unknown"
    assert events == []


def test_job_close_exception_preserves_unknown_owner():
    owned, events = owner()

    def fail_close(handle):
        events.append(("job", handle))
        raise OSError("injected job-close ambiguity")

    owned.job_api.close = fail_close
    with pytest.raises(UnknownBuildxOwnerCleanup) as caught:
        owned.close()
    assert caught.value.owner is owned and owned.state == "unknown"
    assert events == ["attributes", ("job", 71)]
