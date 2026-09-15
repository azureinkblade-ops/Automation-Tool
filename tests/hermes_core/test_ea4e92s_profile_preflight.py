"""Fake profile preflight tests; no profile, filesystem, or native operation."""

from dataclasses import replace

import pytest

from tools import ea4e92s_profile_preflight as subject


PIN = b"\x01\x01\0\0\0\0\0\x0f\x02\0\0\0"
FILE_ID = bytes(range(16))
PATH = r"C:\Users\David\AppData\Local\Packages\Hermes.Parser"


def snapshot():
    return subject.ProfileSnapshot(
        "reviewed-profile", PIN, PATH, 1234, FILE_ID, False)


DEFAULT = object()


class Api:
    def __init__(self, value=DEFAULT):
        self.value = snapshot() if value is DEFAULT else value
        self.calls = []

    def inspect(self, name):
        self.calls.append(name)
        return self.value


def review(api=None, **changes):
    values = {
        "profile_name": "reviewed-profile",
        "expected_sid": PIN,
        "expected_storage_path": PATH,
        "expected_volume_serial": 1234,
        "expected_file_id": FILE_ID,
    }
    values.update(changes)
    return subject.review_existing_profile(api or Api(), **values)


def test_exact_snapshot_returns_immutable_reviewed_identity():
    api = Api()
    result = review(api)
    assert result == subject.ReviewedProfile(
        "reviewed-profile", PIN, PATH.lower(), 1234, FILE_ID)
    assert api.calls == ["reviewed-profile"]
    with pytest.raises(Exception):
        result.profile_name = "changed"


@pytest.mark.parametrize("value", [None, "", "bad\0name", 1])
def test_invalid_profile_name_denied_before_inspection(value):
    api = Api()
    with pytest.raises(ValueError):
        review(api, profile_name=value)
    assert api.calls == []


@pytest.mark.parametrize("value", [None, bytearray(PIN), b"", b"a" * 69])
def test_invalid_sid_pin_denied_before_inspection(value):
    api = Api()
    with pytest.raises(ValueError):
        review(api, expected_sid=value)
    assert api.calls == []


@pytest.mark.parametrize("value", [
    None, "", r"relative\path", r"\\server\share\path", r"1:\path",
    "C:\\", r"C:/mixed/path", "C:\\bad\0path", r"C:\path\..\escape",
    r"C:\path\.\child", r"C:\path\\child", r"C:\path\child\\",
    "C:\\path\\name ", "C:\\path\\name.", r"C:\path\bad:name",
    r"C:\path\bad<name", r"C:\path\CON", r"C:\path\com1.txt",
    "C:\\path\\control\x01name", r"C:\path\wild*name",
])
def test_noncanonical_path_pin_denied_before_inspection(value):
    api = Api()
    with pytest.raises(ValueError):
        review(api, expected_storage_path=value)
    assert api.calls == []


@pytest.mark.parametrize("value", [None, True, -1, 1 << 64, "1234"])
def test_invalid_volume_pin_denied_before_inspection(value):
    api = Api()
    with pytest.raises(ValueError):
        review(api, expected_volume_serial=value)
    assert api.calls == []


@pytest.mark.parametrize("value", [None, bytearray(FILE_ID), b"", b"a" * 15, b"a" * 17])
def test_invalid_file_id_pin_denied_before_inspection(value):
    api = Api()
    with pytest.raises(ValueError):
        review(api, expected_file_id=value)
    assert api.calls == []


@pytest.mark.parametrize("field,value", [
    ("profile_name", "other"), ("sid", b"b" * 12),
    ("sid", bytearray(PIN)),
    ("storage_path", r"C:\Other\Folder"), ("volume_serial", 1235),
    ("volume_serial", True), ("file_id", b"b" * 16),
    ("file_id", bytearray(FILE_ID)), ("is_reparse_point", True),
    ("is_reparse_point", 0),
])
def test_snapshot_mismatch_denied(field, value):
    api = Api(replace(snapshot(), **{field: value}))
    with pytest.raises(ValueError, match="reviewed identity"):
        review(api)
    assert api.calls == ["reviewed-profile"]


@pytest.mark.parametrize("value", [None, {}, object()])
def test_non_snapshot_result_denied(value):
    api = Api(value)
    with pytest.raises(ValueError, match="exact profile snapshot"):
        review(api)
    assert api.calls == ["reviewed-profile"]


def test_case_only_path_difference_matches_windows_identity():
    api = Api(replace(snapshot(), storage_path=PATH.upper()))
    assert review(api).storage_path == PATH.lower()


def test_inspection_exception_is_preserved_without_fabricated_result():
    class FailingApi:
        def inspect(self, name):
            raise OSError("scripted inspection uncertainty")

    with pytest.raises(OSError, match="uncertainty"):
        review(FailingApi())
