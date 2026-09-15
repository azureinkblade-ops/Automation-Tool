"""Injected Windows profile-inspection tests; no native function is called."""

import pytest

from tools import ea4e92s_windows_profile as subject
from tools.ea4e92s_windows_sid import PartialSidDerivation


PIN = b"\x01\x01\0\0\0\0\0\x0f\x02\0\0\0"
PATH = r"C:\Users\David\AppData\Local\Packages\Hermes.Parser"
FILE_ID = bytes(range(16))


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class SidApi:
    def __init__(self, events, valid=True, release=True):
        self.events, self.valid, self.release = events, valid, release

    def derive(self, name):
        self.events.append(("derive", name))
        return 91

    def is_valid(self, pointer):
        self.events.append(("valid", pointer))
        return self.valid

    def length(self, pointer):
        self.events.append(("length", pointer))
        return len(PIN)

    def read(self, pointer, length):
        self.events.append(("read", pointer, length))
        return PIN

    def free(self, pointer):
        self.events.append(("free_sid", pointer))
        return self.release


class Advapi:
    def __init__(self, events, result=1, pointer=101):
        self.events, self.result, self.pointer = events, result, pointer
        self.ConvertSidToStringSidW = Function(self.convert)

    def convert(self, sid, output):
        self.events.append(("convert", sid))
        output._obj.value = self.pointer
        return self.result


class UserEnv:
    def __init__(self, events, result=0, pointer=102):
        self.events, self.result, self.pointer = events, result, pointer
        self.GetAppContainerFolderPath = Function(self.folder)

    def folder(self, sid_text, output):
        self.events.append(("folder", sid_text))
        output._obj.value = self.pointer
        return self.result


class Ole32:
    def __init__(self, events, fail=False):
        self.events, self.fail = events, fail
        self.CoTaskMemFree = Function(self.free)

    def free(self, pointer):
        self.events.append(("free_path", pointer))
        if self.fail:
            raise OSError("scripted path free failure")


class Kernel:
    def __init__(self, events, handle=103, attributes=0x10,
                 fail_attribute=False, fail_identity=False,
                 close=True, local_free=None):
        self.events = events
        self.handle = handle
        self.attributes = attributes
        self.fail_attribute = fail_attribute
        self.fail_identity = fail_identity
        self.close_result = close
        self.local_free_result = local_free
        self.CreateFileW = Function(self.create)
        self.GetFileInformationByHandleEx = Function(self.info)
        self.CloseHandle = Function(self.close)
        self.LocalFree = Function(self.local_free)

    def create(self, path, access, share, security, disposition, flags, template):
        self.events.append(("open", path, access, share, disposition, flags))
        assert security is template is None
        return self.handle

    def info(self, handle, info_class, output, size):
        self.events.append(("info", info_class, handle))
        if info_class == subject.FILE_ATTRIBUTE_TAG_INFO_CLASS:
            output._obj.FileAttributes = self.attributes
            output._obj.ReparseTag = 0
            return int(not self.fail_attribute)
        output._obj.VolumeSerialNumber = 1234
        for index, value in enumerate(FILE_ID):
            output._obj.FileId.Identifier[index] = value
        return int(not self.fail_identity)

    def close(self, handle):
        self.events.append(("close", handle))
        return self.close_result

    def local_free(self, pointer):
        self.events.append(("free_sid_text", pointer))
        return self.local_free_result


def adapter(events, sid=None, user=None, advapi=None, ole=None, kernel=None,
            values=None):
    strings = values or {101: "S-1-15-2-1", 102: PATH}
    return subject.WindowsProfileApi(
        sid or SidApi(events), user or UserEnv(events),
        advapi or Advapi(events), ole or Ole32(events),
        kernel or Kernel(events), lambda pointer: strings[pointer])


def test_inspection_returns_exact_snapshot_after_ordered_queries_and_cleanup():
    events = []
    snapshot = adapter(events).inspect("reviewed-profile")
    assert snapshot == subject.ProfileSnapshot(
        "reviewed-profile", PIN, PATH, 1234, FILE_ID, False)
    assert [event[0] for event in events] == [
        "derive", "valid", "length", "read", "convert", "folder", "open",
        "info", "info", "close", "free_path", "free_sid_text", "free_sid"]
    opened = events[6]
    assert opened[2:] == (0, 7, 3, 0x02200000)


@pytest.mark.parametrize("name", [None, "", "bad\0name", 1])
def test_invalid_profile_name_denied_before_any_collaborator(name):
    events = []
    with pytest.raises(ValueError, match="profile name"):
        adapter(events).inspect(name)
    assert events == []


def test_invalid_sid_is_released_before_failure_returns():
    events = []
    with pytest.raises(OSError, match="invalid SID"):
        adapter(events, sid=SidApi(events, valid=False)).inspect("reviewed-profile")
    assert [event[0] for event in events] == ["derive", "valid", "free_sid"]


@pytest.mark.parametrize("stage", ["convert", "folder", "open", "attribute", "identity"])
def test_each_native_failure_releases_every_acquired_resource(stage):
    events = []
    kwargs = {}
    if stage == "convert":
        kwargs["advapi"] = Advapi(events, result=0, pointer=None)
    elif stage == "folder":
        kwargs["user"] = UserEnv(events, result=-1, pointer=None)
    elif stage == "open":
        kwargs["kernel"] = Kernel(events, handle=subject.INVALID_HANDLE_VALUE)
    elif stage == "attribute":
        kwargs["kernel"] = Kernel(events, fail_attribute=True)
    else:
        kwargs["kernel"] = Kernel(events, fail_identity=True)
    with pytest.raises(OSError):
        adapter(events, **kwargs).inspect("reviewed-profile")
    names = [event[0] for event in events]
    assert names[-1] == "free_sid"
    if stage != "convert":
        assert "free_sid_text" in names
    if stage not in ("convert", "folder"):
        assert "free_path" in names
    if stage in ("attribute", "identity"):
        assert "close" in names


def test_reparse_status_is_reported_for_value_level_rejection():
    events = []
    value = adapter(events, kernel=Kernel(events, attributes=0x410)).inspect(
        "reviewed-profile")
    assert value.is_reparse_point is True


def test_non_directory_handle_is_denied_and_cleaned():
    events = []
    with pytest.raises(OSError, match="directory"):
        adapter(events, kernel=Kernel(events, attributes=0)).inspect(
            "reviewed-profile")
    assert [event[0] for event in events][-4:] == [
        "close", "free_path", "free_sid_text", "free_sid"]


@pytest.mark.parametrize("resource", ["handle", "path", "sid_text", "sid"])
def test_cleanup_uncertainty_blocks_retry_and_preserves_resource_evidence(resource):
    events = []
    kwargs = {}
    if resource == "handle":
        kwargs["kernel"] = Kernel(events, close=False)
    elif resource == "path":
        kwargs["ole"] = Ole32(events, fail=True)
    elif resource == "sid_text":
        kwargs["kernel"] = Kernel(events, local_free=101)
    else:
        kwargs["sid"] = SidApi(events, release=False)
    api = adapter(events, **kwargs)
    with pytest.raises(subject.UnknownProfileInspection) as caught:
        api.inspect("reviewed-profile")
    assert caught.value.api is api and api.uncertain is True
    before = list(events)
    with pytest.raises(subject.UnknownProfileInspection, match="reconciliation"):
        api.inspect("reviewed-profile")
    assert events == before


@pytest.mark.parametrize("pointer,value", [(101, None), (101, 7), (102, None), (102, 7)])
def test_malformed_native_string_is_denied_after_owned_cleanup(pointer, value):
    events = []
    values = {101: "S-1-15-2-1", 102: PATH}
    values[pointer] = value
    with pytest.raises(OSError, match="string"):
        adapter(events, values=values).inspect("reviewed-profile")
    assert [event[0] for event in events][-1] == "free_sid"


@pytest.mark.parametrize("stage", ["sid_text", "path"])
def test_partial_output_on_failed_call_is_retained_and_blocks_retry(stage):
    events = []
    kwargs = ({"advapi": Advapi(events, result=0, pointer=101)}
              if stage == "sid_text"
              else {"user": UserEnv(events, result=-1, pointer=102)})
    api = adapter(events, **kwargs)
    with pytest.raises(subject.UnknownProfileInspection) as caught:
        api.inspect("reviewed-profile")
    assert caught.value.resources is api.uncertain_resources
    names = [event[0] for event in events]
    assert ("free_sid_text" not in names if stage == "sid_text"
            else "free_path" not in names)
    assert names[-1] == "free_sid"
    before = list(events)
    with pytest.raises(subject.UnknownProfileInspection, match="reconciliation"):
        api.inspect("reviewed-profile")
    assert events == before


def test_partial_sid_derivation_is_retained_and_blocks_retry():
    events = []

    class PartialSid(SidApi):
        def derive(self, name):
            self.events.append(("derive", name))
            raise PartialSidDerivation("scripted partial SID", self, 91)

        def free(self, pointer):
            self.events.append(("blocked_free_sid", pointer))
            raise ValueError("SID pointer is not safely releasable")

    api = adapter(events, sid=PartialSid(events))
    with pytest.raises(subject.UnknownProfileInspection) as caught:
        api.inspect("reviewed-profile")
    assert caught.value.resources.sid_pointer == 91
    before = list(events)
    with pytest.raises(subject.UnknownProfileInspection, match="reconciliation"):
        api.inspect("reviewed-profile")
    assert events == before


@pytest.mark.parametrize("stage", ["sid_text", "path"])
def test_success_with_invalid_nonnull_output_is_not_speculatively_freed(stage):
    events = []
    kwargs = ({"advapi": Advapi(events, result=1,
                                 pointer=subject.INVALID_HANDLE_VALUE)}
              if stage == "sid_text"
              else {"user": UserEnv(events, result=0,
                                    pointer=subject.INVALID_HANDLE_VALUE)})
    api = adapter(events, **kwargs)
    with pytest.raises(subject.UnknownProfileInspection):
        api.inspect("reviewed-profile")
    names = [event[0] for event in events]
    assert ("free_sid_text" not in names if stage == "sid_text"
            else "free_path" not in names)
    assert api.uncertain is True and names[-1] == "free_sid"


@pytest.mark.parametrize("missing", ["sid", "user", "advapi", "ole", "kernel", "reader"])
def test_injected_construction_requires_complete_collaborators(missing):
    events = []
    values = {
        "sid_api": SidApi(events), "userenv": UserEnv(events),
        "advapi": Advapi(events), "ole32": Ole32(events),
        "kernel32": Kernel(events), "wide_reader": lambda pointer: PATH,
    }
    values[{"sid": "sid_api", "user": "userenv", "advapi": "advapi",
            "ole": "ole32", "kernel": "kernel32", "reader": "wide_reader"}[missing]] = None
    with pytest.raises((ValueError, OSError)):
        subject.WindowsProfileApi(**values)
