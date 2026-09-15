"""Test-owned AppContainer profile preflight; no native calls or mutation."""

import ntpath
from dataclasses import dataclass


RESERVED_COMPONENTS = {"CON", "PRN", "AUX", "NUL"}
RESERVED_COMPONENTS.update(f"COM{number}" for number in range(1, 10))
RESERVED_COMPONENTS.update(f"LPT{number}" for number in range(1, 10))


@dataclass(frozen=True)
class ProfileSnapshot:
    profile_name: str
    sid: bytes
    storage_path: str
    volume_serial: int
    file_id: bytes
    is_reparse_point: bool


@dataclass(frozen=True)
class ReviewedProfile:
    profile_name: str
    sid: bytes
    storage_path: str
    volume_serial: int
    file_id: bytes


def canonical_local_path(value):
    if type(value) is not str or not value or "\0" in value or "/" in value:
        raise ValueError("canonical local Windows path required")
    drive, tail = ntpath.splitdrive(value)
    if (len(drive) != 2 or not drive[0].isalpha() or drive[1] != ":"
            or not tail.startswith("\\")):
        raise ValueError("absolute drive path required")
    parts = [part for part in tail.split("\\") if part]
    if not parts or any(part in (".", "..") for part in parts):
        raise ValueError("normalized non-root storage path required")
    for part in parts:
        stem = part.split(".", 1)[0].upper()
        if (part.endswith((" ", ".")) or stem in RESERVED_COMPONENTS
                or any(ord(character) < 32 or character in '<>:"|?*'
                       for character in part)):
            raise ValueError("canonical storage component required")
    normalized = ntpath.normpath(value)
    if ntpath.normcase(value) != ntpath.normcase(normalized):
        raise ValueError("pre-normalized storage path required")
    return ntpath.normcase(normalized)


def review_existing_profile(api, profile_name, expected_sid, expected_storage_path,
                            expected_volume_serial, expected_file_id):
    """Match one injected profile snapshot against independent reviewed pins.

    A future native inspector must collect path identity without following a
    reparse point and close its own handles. This value-level contract does not
    prove inspection freshness, ACLs, token identity, or runtime isolation.
    """
    if type(profile_name) is not str or not profile_name or "\0" in profile_name:
        raise ValueError("explicit profile name required")
    if type(expected_sid) is not bytes or not 8 <= len(expected_sid) <= 68:
        raise ValueError("bounded reviewed SID required")
    canonical_path = canonical_local_path(expected_storage_path)
    if (type(expected_volume_serial) is not int
            or not 0 <= expected_volume_serial < 1 << 64):
        raise ValueError("reviewed volume identity required")
    if type(expected_file_id) is not bytes or len(expected_file_id) != 16:
        raise ValueError("reviewed 128-bit file identity required")

    snapshot = api.inspect(profile_name)
    if type(snapshot) is not ProfileSnapshot:
        raise ValueError("exact profile snapshot required")
    if (type(snapshot.profile_name) is not str or type(snapshot.sid) is not bytes
            or type(snapshot.volume_serial) is not int
            or type(snapshot.file_id) is not bytes
            or snapshot.profile_name != profile_name or snapshot.sid != expected_sid
            or canonical_local_path(snapshot.storage_path) != canonical_path
            or snapshot.volume_serial != expected_volume_serial
            or snapshot.file_id != expected_file_id
            or snapshot.is_reparse_point is not False):
        raise ValueError("profile snapshot does not match reviewed identity")
    return ReviewedProfile(
        profile_name, expected_sid, canonical_path,
        expected_volume_serial, expected_file_id)
