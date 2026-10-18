"""Pure comparison of an expected app package with a complete observed inventory."""

from dataclasses import dataclass
import re

from tools.hermes_core.hashing import sha256_payload


_HASH = re.compile(r"[0-9a-f]{64}\Z")
_COMPONENT = re.compile(r"[A-Za-z0-9_. -]+\Z")
_MAX_FILES = 50000
_DEVICE = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in range(1, 10)
}


class PackageInventoryDenied(ValueError):
    """The observed package cannot establish the expected complete file set."""


@dataclass(frozen=True)
class ExpectedPackageFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ObservedPackageFile:
    path: str
    sha256: str
    size: int
    volume_serial: int
    file_index: int
    link_count: int
    reparse_point: bool


@dataclass(frozen=True)
class CompletePackageInventory:
    root_volume_serial: int
    root_file_index: int
    complete: bool
    files: tuple[ObservedPackageFile, ...]


def _path_key(path):
    if type(path) is not str or not path or len(path) > 1024 or "\\" in path:
        raise PackageInventoryDenied("package path form denied")
    for part in path.split("/"):
        if (not part or not _COMPONENT.fullmatch(part)
                or part in {".", ".."} or part.endswith((".", " "))
                or part.split(".", 1)[0].upper() in _DEVICE):
            raise PackageInventoryDenied("package path component denied")
    return path.casefold()


def compare_package_inventory(
    expected: tuple[ExpectedPackageFile, ...],
    observed: CompletePackageInventory,
) -> str:
    """Return a manifest digest only for an exact, complete inventory match.

    The caller must independently establish the protected root, trustworthy
    enumeration, and retained file identities. This function performs no I/O.
    """
    if (type(expected) is not tuple or not 0 < len(expected) <= _MAX_FILES
            or type(observed) is not CompletePackageInventory
            or observed.complete is not True
            or type(observed.root_volume_serial) is not int
            or not 0 < observed.root_volume_serial <= 0xFFFFFFFF
            or type(observed.root_file_index) is not int
            or not 0 < observed.root_file_index <= 0xFFFFFFFFFFFFFFFF
            or type(observed.files) is not tuple
            or len(observed.files) != len(expected)):
        raise PackageInventoryDenied("package inventory incomplete or malformed")
    expected_by_key = {}
    for item in expected:
        if (type(item) is not ExpectedPackageFile
                or type(item.sha256) is not str or not _HASH.fullmatch(item.sha256)
                or type(item.size) is not int or item.size < 0):
            raise PackageInventoryDenied("expected package file malformed")
        key = _path_key(item.path)
        if key in expected_by_key:
            raise PackageInventoryDenied("expected package path collision")
        expected_by_key[key] = item
    observed_keys = set()
    object_ids = {(observed.root_volume_serial, observed.root_file_index)}
    for item in observed.files:
        if (type(item) is not ObservedPackageFile
                or type(item.sha256) is not str or not _HASH.fullmatch(item.sha256)
                or type(item.size) is not int or item.size < 0
                or type(item.volume_serial) is not int
                or item.volume_serial != observed.root_volume_serial
                or type(item.file_index) is not int or item.file_index <= 0
                or type(item.link_count) is not int or item.link_count != 1
                or item.reparse_point is not False):
            raise PackageInventoryDenied("observed package file unsafe")
        key = _path_key(item.path)
        object_id = (item.volume_serial, item.file_index)
        if key in observed_keys or object_id in object_ids:
            raise PackageInventoryDenied("observed package identity collision")
        observed_keys.add(key)
        object_ids.add(object_id)
        wanted = expected_by_key.get(key)
        if (wanted is None or item.path != wanted.path
                or item.sha256 != wanted.sha256 or item.size != wanted.size):
            raise PackageInventoryDenied("observed package differs from manifest")
    if observed_keys != set(expected_by_key):
        raise PackageInventoryDenied("package file set differs from manifest")
    return sha256_payload({
        "schema_version": "ea4e92mf-app-package-inventory-v1",
        "files": [
            {"path": item.path, "sha256": item.sha256, "size": item.size}
            for item in sorted(expected, key=lambda entry: entry.path)
        ],
    })
