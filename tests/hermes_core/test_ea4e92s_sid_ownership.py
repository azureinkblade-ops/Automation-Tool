"""Scripted SID identity/cleanup tests; no Windows calls or profile changes."""

import pytest

from tools import ea4e92s_sid_ownership as subject


PIN = b"\x01\x01\0\0\0\0\0\x0f\x02\0\0\0"


class SidApi:
    def __init__(self, events, valid=True, length=12, value=PIN, free=True):
        self.events = events
        self.valid, self.size, self.value, self.release = valid, length, value, free

    def derive(self, name):
        assert name == "reviewed-profile"
        self.events.append("derive")
        return 91

    def is_valid(self, pointer):
        assert pointer == 91
        self.events.append("valid")
        return self.valid

    def length(self, pointer):
        self.events.append("length")
        return self.size

    def read(self, pointer, length):
        assert (pointer, length) == (91, 12)
        self.events.append("read")
        return self.value

    def free(self, pointer):
        assert pointer == 91
        self.events.append("free")
        if self.release == "exception":
            raise OSError("scripted free failure")
        return self.release


class AttributeApi:
    def __init__(self, events, update=True, destroy=True):
        self.events, self.applied, self.deleted = events, update, destroy
        self.handle = object()

    def create(self, count):
        assert count == 2
        self.events.append("create")
        return self.handle

    def update(self, handle, key, value):
        assert handle is self.handle
        self.events.append(key)
        return self.applied

    def destroy(self, handle):
        self.events.append("destroy")
        return self.deleted


def prepare(events, sid=None, attributes=None, name="reviewed-profile", pin=PIN):
    return subject.prepare_reviewed_security(
        sid or SidApi(events), attributes or AttributeApi(events), 71, name, pin)


def test_verified_identity_and_ordered_cleanup():
    events = []
    owned = prepare(events)
    assert events == ["derive", "valid", "length", "read", "create",
                      "JOB_LIST", "SECURITY_CAPABILITIES"]
    assert owned.attributes.keepalive[-1] is owned
    owned.close()
    owned.close()
    assert events[-2:] == ["destroy", "free"]
    assert events.count("free") == 1
    assert owned.state == "closed" and owned.pointer == 0


@pytest.mark.parametrize("name", [None, "", "bad\0name", 1])
def test_invalid_name_before_derive(name):
    events = []
    with pytest.raises(ValueError):
        prepare(events, name=name)
    assert events == []


@pytest.mark.parametrize("pin", [None, bytearray(PIN), b"", b"a" * 69])
def test_unbound_or_unbounded_pin_before_derive(pin):
    events = []
    with pytest.raises(ValueError):
        prepare(events, pin=pin)
    assert events == []


@pytest.mark.parametrize("valid", [False, None, 1])
def test_invalid_sid_never_reads_or_composes(valid):
    events = []
    with pytest.raises(ValueError):
        prepare(events, sid=SidApi(events, valid=valid))
    assert events == ["derive", "valid", "free"]


@pytest.mark.parametrize("length", [0, 68, True, "12"])
def test_length_mismatch_never_reads(length):
    events = []
    with pytest.raises(ValueError):
        prepare(events, sid=SidApi(events, length=length))
    assert events == ["derive", "valid", "length", "free"]


@pytest.mark.parametrize("value", [b"b" * 12, bytearray(PIN), None])
def test_identity_mismatch_never_composes(value):
    events = []
    with pytest.raises(ValueError):
        prepare(events, sid=SidApi(events, value=value))
    assert "create" not in events and events[-1] == "free"


def test_partial_attribute_failure_frees_in_order():
    events = []
    with pytest.raises(OSError):
        prepare(events, attributes=AttributeApi(events, update=False))
    assert events[-2:] == ["destroy", "free"]


def test_uncertain_attribute_cleanup_retains_sid_without_free():
    events = []
    with pytest.raises(subject.UnknownSidCleanup) as caught:
        prepare(events, attributes=AttributeApi(events, update=False, destroy=False))
    owned = caught.value.owned
    assert owned.pointer == 91 and owned.attributes.state == "unknown"
    assert "free" not in events
    with pytest.raises(subject.UnknownSidCleanup):
        owned.close()
    assert events.count("destroy") == 1


@pytest.mark.parametrize("free", [False, None, 1, "exception"])
def test_uncertain_sid_cleanup_retains_evidence_and_blocks_retry(free):
    events = []
    owned = prepare(events, sid=SidApi(events, free=free))
    with pytest.raises(subject.UnknownSidCleanup) as caught:
        owned.close()
    assert caught.value.owned is owned and owned.pointer == 91
    assert owned.state == "unknown"
    with pytest.raises(subject.UnknownSidCleanup):
        owned.close()
    assert events.count("free") == 1


@pytest.mark.parametrize("method", ["is_valid", "length", "read"])
def test_unrelated_exception_metadata_does_not_claim_attribute_ownership(method):
    events = []
    sid = SidApi(events)
    error = OSError("scripted validation failure")
    error.prepared = object()

    def fail(*args):
        raise error

    setattr(sid, method, fail)
    with pytest.raises(OSError) as caught:
        prepare(events, sid=sid)
    assert caught.value is error
    assert events[-1] == "free" and "create" not in events


@pytest.mark.parametrize("pointer", [None, 0, -1, True, "91", 1 << 64])
def test_invalid_derive_result_does_not_dereference_or_free(pointer):
    events = []
    sid = SidApi(events)
    sid.derive = lambda name: pointer
    with pytest.raises(OSError, match="owned SID pointer"):
        prepare(events, sid=sid)
    assert events == []


def test_derive_exception_preserves_collaborator_evidence():
    events = []
    sid = SidApi(events)
    error = OSError("partial derive requires collaborator reconciliation")
    error.partial_allocation = object()

    def fail(name):
        raise error

    sid.derive = fail
    with pytest.raises(OSError) as caught:
        prepare(events, sid=sid)
    assert caught.value is error
    assert events == []


def test_close_attribute_failure_does_not_free_sid():
    events = []
    owned = prepare(events, attributes=AttributeApi(events, destroy=False))
    with pytest.raises(subject.UnknownSidCleanup) as caught:
        owned.close()
    assert caught.value.owned is owned and owned.pointer == 91
    assert "free" not in events
    with pytest.raises(subject.UnknownSidCleanup):
        owned.close()
    assert events.count("destroy") == 1
