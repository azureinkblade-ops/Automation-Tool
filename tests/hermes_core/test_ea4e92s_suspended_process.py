"""Value-level suspended-process ownership tests; no process is launched."""

import pytest

from tools import ea4e92s_suspended_process as subject


class CreationOwner:
    def __init__(self, state="owned", handle=41):
        self.state = state
        self.security = type("Security", (), {
            "state": state,
            "attributes": type("Attributes", (), {
                "state": state, "handle": handle})(),
        })()


class FakeProcessApi:
    def __init__(self, result=None, create_error=None, terminate=True,
                 close_thread=True, close_process=True, failure=None):
        self.result = result or subject.SuspendedCreationResult(
            process_handle=101, thread_handle=102,
            process_id=201, thread_id=202,
            suspended=True, job_bound_at_creation=True,
            appcontainer_bound_at_creation=True)
        self.create_error = create_error
        self.terminate_result = terminate
        self.close_thread_result = close_thread
        self.close_process_result = close_process
        self.failure = failure
        self.events = []

    def create_suspended(self, attribute_handle):
        self.events.append(("create", attribute_handle))
        if self.create_error is not None:
            raise self.create_error
        return self.result

    def terminate(self, process_handle):
        self.events.append(("terminate", process_handle))
        if self.failure == "terminate":
            raise OSError("scripted terminate failure")
        return self.terminate_result

    def close_thread(self, thread_handle):
        self.events.append(("close_thread", thread_handle))
        if self.failure == "close_thread":
            raise OSError("scripted thread close failure")
        return self.close_thread_result

    def close_process(self, process_handle):
        self.events.append(("close_process", process_handle))
        if self.failure == "close_process":
            raise OSError("scripted process close failure")
        return self.close_process_result


def result(**changes):
    values = {
        "process_handle": 101, "thread_handle": 102,
        "process_id": 201, "thread_id": 202,
        "suspended": True, "job_bound_at_creation": True,
        "appcontainer_bound_at_creation": True,
    }
    values.update(changes)
    return subject.SuspendedCreationResult(**values)


def test_exact_creation_result_becomes_owned_without_resuming():
    api = FakeProcessApi()
    owned = subject.create_owned_suspended_process(api, CreationOwner())
    assert owned.state == "owned"
    assert owned.result == result()
    assert api.events == [("create", 41)]


@pytest.mark.parametrize("owner", [None, CreationOwner("closed"), CreationOwner("unknown")])
def test_unowned_creation_attributes_are_denied_before_creation(owner):
    api = FakeProcessApi()
    with pytest.raises(ValueError, match="owned creation attributes"):
        subject.create_owned_suspended_process(api, owner)
    assert api.events == []


@pytest.mark.parametrize("owner", [object(), type("Owner", (), {"state": "owned"})()])
def test_malformed_creation_owner_is_denied_before_creation(owner):
    api = FakeProcessApi()
    with pytest.raises(ValueError, match="owned creation attributes"):
        subject.create_owned_suspended_process(api, owner)
    assert api.events == []


@pytest.mark.parametrize("handle", [None, 0, -1, True, "41"])
def test_invalid_attribute_handle_is_denied_before_creation(handle):
    api = FakeProcessApi()
    with pytest.raises(ValueError, match="attribute handle"):
        subject.create_owned_suspended_process(api, CreationOwner(handle=handle))
    assert api.events == []


def test_creation_exception_is_unknown_and_never_retried_here():
    api = FakeProcessApi(create_error=OSError("ambiguous creation"))
    with pytest.raises(subject.UnknownSuspendedProcess) as caught:
        subject.create_owned_suspended_process(api, CreationOwner())
    assert caught.value.owned is None
    assert api.events == [("create", 41)]


@pytest.mark.parametrize("bad", [None, object(), {"process_handle": 101}])
def test_noncanonical_creation_result_is_unknown(bad):
    api = FakeProcessApi(result=result())
    api.result = bad
    with pytest.raises(subject.UnknownSuspendedProcess) as caught:
        subject.create_owned_suspended_process(api, CreationOwner())
    assert caught.value.owned is None


@pytest.mark.parametrize("field,value", [
    ("process_handle", 0), ("process_handle", True),
    ("thread_handle", -1), ("thread_handle", "102"),
])
def test_invalid_creation_handle_is_unknown(field, value):
    api = FakeProcessApi(result=result(**{field: value}))
    with pytest.raises(subject.UnknownSuspendedProcess) as caught:
        subject.create_owned_suspended_process(api, CreationOwner())
    assert caught.value.owned is None


@pytest.mark.parametrize("field,value", [
    ("process_id", 0), ("process_id", True),
    ("thread_id", -1), ("thread_id", "202"),
])
def test_invalid_creation_id_is_cleaned_and_denied(field, value):
    api = FakeProcessApi(result=result(**{field: value}))
    with pytest.raises(subject.SuspendedProcessDenied, match="creation identity"):
        subject.create_owned_suspended_process(api, CreationOwner())
    assert [event[0] for event in api.events] == [
        "create", "terminate", "close_thread", "close_process"]


def test_aliased_process_and_thread_handles_are_unknown():
    api = FakeProcessApi(result=result(thread_handle=101))
    with pytest.raises(subject.UnknownSuspendedProcess):
        subject.create_owned_suspended_process(api, CreationOwner())
    assert api.events == [("create", 41)]


@pytest.mark.parametrize("field,value", [
    ("suspended", False), ("suspended", 1),
    ("job_bound_at_creation", False), ("job_bound_at_creation", 1),
    ("appcontainer_bound_at_creation", False),
    ("appcontainer_bound_at_creation", 1),
])
def test_unproven_creation_predicate_is_terminated_and_denied(field, value):
    api = FakeProcessApi(result=result(**{field: value}))
    with pytest.raises(subject.SuspendedProcessDenied, match="creation predicate"):
        subject.create_owned_suspended_process(api, CreationOwner())
    assert api.events == [
        ("create", 41), ("terminate", 101),
        ("close_thread", 102), ("close_process", 101)]


def test_close_terminates_before_closing_thread_then_process_and_is_idempotent():
    api = FakeProcessApi()
    owned = subject.create_owned_suspended_process(api, CreationOwner())
    owned.close()
    owned.close()
    assert owned.state == "closed"
    assert api.events == [
        ("create", 41), ("terminate", 101),
        ("close_thread", 102), ("close_process", 101)]


@pytest.mark.parametrize("stage", ["terminate", "close_thread", "close_process"])
def test_cleanup_exception_attempts_remaining_closes_and_blocks_retry(stage):
    api = FakeProcessApi(failure=stage)
    owned = subject.create_owned_suspended_process(api, CreationOwner())
    with pytest.raises(subject.UnknownSuspendedProcess) as caught:
        owned.close()
    assert caught.value.owned is owned and owned.state == "unknown"
    expected = (["create", "terminate"] if stage == "terminate" else
                ["create", "terminate", "close_thread", "close_process"])
    assert [event[0] for event in api.events] == expected
    before = list(api.events)
    with pytest.raises(subject.UnknownSuspendedProcess, match="reconciliation"):
        owned.close()
    assert api.events == before


@pytest.mark.parametrize("stage", ["terminate", "close_thread", "close_process"])
def test_non_true_cleanup_result_is_unknown(stage):
    kwargs = {stage: None}
    api = FakeProcessApi(**kwargs)
    owned = subject.create_owned_suspended_process(api, CreationOwner())
    with pytest.raises(subject.UnknownSuspendedProcess):
        owned.close()
    assert owned.state == "unknown"
    if stage == "terminate":
        assert [event[0] for event in api.events] == ["create", "terminate"]


def test_denied_predicate_with_uncertain_cleanup_preserves_owned_evidence():
    api = FakeProcessApi(result=result(suspended=False), terminate=False)
    with pytest.raises(subject.UnknownSuspendedProcess) as caught:
        subject.create_owned_suspended_process(api, CreationOwner())
    assert caught.value.owned is not None
    assert caught.value.owned.state == "unknown"


def test_incomplete_cleanup_collaborator_normalizes_to_unknown():
    class IncompleteApi:
        def create_suspended(self, attribute_handle):
            return result()

        def terminate(self, process_handle):
            return True

        def close_process(self, process_handle):
            return True

    owned = subject.create_owned_suspended_process(IncompleteApi(), CreationOwner())
    with pytest.raises(subject.UnknownSuspendedProcess) as caught:
        owned.close()
    assert caught.value.owned is owned and owned.state == "unknown"


def test_source_has_no_native_or_runtime_launch_capability():
    source = subject.__file__
    text = open(source, encoding="utf-8").read()
    for forbidden in (
            "subprocess", "WinDLL", "CreateProcessW", "Popen", "shell=True",
            "resume_thread", "socket", "requests", "ComfyUI"):
        assert forbidden not in text
