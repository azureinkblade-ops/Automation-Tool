"""Injected Windows SID adapter tests; no native DLL or profile operation."""

import pytest

from tools import ea4e92s_windows_sid as subject


PIN = b"\x01\x01\0\0\0\0\0\x0f\x02\0\0\0"


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class UserEnv:
    def __init__(self, result=0, pointer=91):
        self.result, self.pointer, self.events = result, pointer, []
        self.DeriveAppContainerSidFromAppContainerName = Function(self.derive)

    def derive(self, name, output):
        self.events.append(("derive", name))
        output._obj.value = self.pointer
        return self.result


class Advapi:
    def __init__(self, valid=1, length=12, free=None):
        self.valid, self.size, self.release = valid, length, free
        self.events = []
        self.IsValidSid = Function(self.is_valid)
        self.GetLengthSid = Function(self.length)
        self.FreeSid = Function(self.free)

    def is_valid(self, pointer):
        self.events.append(("valid", pointer))
        return self.valid

    def length(self, pointer):
        self.events.append(("length", pointer))
        return self.size

    def free(self, pointer):
        self.events.append(("free", pointer))
        return self.release


def adapter(user=None, advapi=None, value=PIN):
    return subject.WindowsSidApi(
        user or UserEnv(), advapi or Advapi(), lambda pointer, length: value)


def test_exact_derive_validate_read_and_free_lifecycle():
    user, security = UserEnv(), Advapi()
    api = adapter(user, security)
    pointer = api.derive("reviewed-profile")
    assert api.is_valid(pointer) is True
    assert api.length(pointer) == len(PIN)
    assert api.read(pointer, len(PIN)) == PIN
    assert api.free(pointer) is True
    assert user.events == [("derive", "reviewed-profile")]
    assert security.events == [("valid", 91), ("length", 91), ("free", 91)]
    assert api.owned == set()


@pytest.mark.parametrize("name", [None, "", "bad\0name", 1])
def test_invalid_name_denied_before_dll(name):
    user = UserEnv()
    with pytest.raises(ValueError):
        adapter(user).derive(name)
    assert user.events == []


def test_failure_without_output_raises_without_ownership():
    api = adapter(UserEnv(result=-1, pointer=None))
    with pytest.raises(OSError, match="derivation failed"):
        api.derive("reviewed-profile")
    assert api.owned == set()


def test_failure_with_output_preserves_partial_allocation_evidence():
    api = adapter(UserEnv(result=-1))
    with pytest.raises(subject.PartialSidDerivation) as caught:
        api.derive("reviewed-profile")
    assert caught.value.api is api and caught.value.pointer == 91
    assert api.owned == api.uncertain == {91}
    with pytest.raises(ValueError, match="safely releasable"):
        api.free(91)


def test_duplicate_pointer_is_not_accepted_as_new_ownership():
    api = adapter()
    assert api.derive("reviewed-profile") == 91
    with pytest.raises(subject.PartialSidDerivation) as caught:
        api.derive("reviewed-profile")
    assert caught.value.pointer == 91
    assert api.owned == api.uncertain == {91}
    with pytest.raises(ValueError, match="releasable"):
        api.free(91)


@pytest.mark.parametrize("pointer", [None, 0])
def test_success_without_positive_pointer_denied(pointer):
    api = adapter(UserEnv(pointer=pointer))
    with pytest.raises(OSError, match="invalid"):
        api.derive("reviewed-profile")
    assert api.owned == set()


def test_length_requires_successful_validity():
    api = adapter(advapi=Advapi(valid=0))
    pointer = api.derive("reviewed-profile")
    assert api.is_valid(pointer) is False
    with pytest.raises(ValueError, match="validity"):
        api.length(pointer)
    assert api.free(pointer) is True


@pytest.mark.parametrize("length", [0, 7, 69, True, "12"])
def test_invalid_native_length_denied(length):
    api = adapter(advapi=Advapi(length=length))
    pointer = api.derive("reviewed-profile")
    assert api.is_valid(pointer) is True
    with pytest.raises(OSError, match="bounds"):
        api.length(pointer)
    assert api.free(pointer) is True


def test_read_requires_exact_recorded_length():
    api = adapter()
    pointer = api.derive("reviewed-profile")
    assert api.is_valid(pointer) is True
    assert api.length(pointer) == 12
    with pytest.raises(ValueError, match="exact"):
        api.read(pointer, 11)
    assert api.free(pointer) is True


@pytest.mark.parametrize("value", [None, bytearray(PIN), b"short"])
def test_malformed_reader_result_denied(value):
    api = adapter(value=value)
    pointer = api.derive("reviewed-profile")
    assert api.is_valid(pointer) is True and api.length(pointer) == 12
    with pytest.raises(OSError, match="unexpected"):
        api.read(pointer, 12)
    assert api.free(pointer) is True


@pytest.mark.parametrize("foreign", [None, 0, 92, True, "91"])
def test_foreign_pointer_operations_denied(foreign):
    api = adapter()
    for operation in (api.is_valid, api.length, lambda pointer: api.read(pointer, 12), api.free):
        with pytest.raises(ValueError):
            operation(foreign)


@pytest.mark.parametrize("result", [91, 1, False])
def test_uncertain_free_retains_pointer_and_blocks_retry(result):
    security = Advapi(free=result)
    api = adapter(advapi=security)
    pointer = api.derive("reviewed-profile")
    assert api.free(pointer) is False
    assert api.owned == api.uncertain == {91}
    with pytest.raises(ValueError, match="releasable"):
        api.free(pointer)
    assert security.events.count(("free", 91)) == 1


def test_free_exception_retains_pointer_and_blocks_retry():
    security = Advapi()

    def fail(pointer):
        security.events.append(("free", pointer))
        raise OSError("scripted FreeSid exception")

    security.FreeSid.implementation = fail
    api = adapter(advapi=security)
    pointer = api.derive("reviewed-profile")
    with pytest.raises(OSError, match="scripted"):
        api.free(pointer)
    assert api.owned == api.uncertain == {91}
    with pytest.raises(ValueError, match="releasable"):
        api.free(pointer)
    assert security.events.count(("free", 91)) == 1


@pytest.mark.parametrize("missing", ["userenv", "advapi", "reader"])
def test_injected_construction_requires_complete_collaborators(missing):
    user, security, reader = UserEnv(), Advapi(), lambda pointer, length: PIN
    if missing == "userenv":
        user = None
    elif missing == "advapi":
        security = None
    else:
        reader = None
    with pytest.raises((ValueError, OSError)):
        subject.WindowsSidApi(user, security, reader)
