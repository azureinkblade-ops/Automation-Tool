"""Pure app-package manifest comparison; no filesystem or process access."""

from dataclasses import replace

import pytest

from tools.hermes_core.app_package_inventory import (
    CompletePackageInventory,
    ExpectedPackageFile,
    ObservedPackageFile,
    PackageInventoryDenied,
    compare_package_inventory,
)


EXPECTED = (
    ExpectedPackageFile("app.py", "a" * 64, 10),
    ExpectedPackageFile("tools/worker.py", "b" * 64, 20),
)
OBSERVED = CompletePackageInventory(
    100, 200, True,
    (
        ObservedPackageFile("app.py", "a" * 64, 10, 100, 201, 1, False),
        ObservedPackageFile("tools/worker.py", "b" * 64, 20, 100, 202, 1, False),
    ),
)


def test_exact_inventory_has_order_independent_manifest_digest():
    first = compare_package_inventory(EXPECTED, OBSERVED)
    assert len(first) == 64
    assert first == compare_package_inventory(EXPECTED[::-1], replace(
        OBSERVED, files=OBSERVED.files[::-1],
    ))


@pytest.mark.parametrize("change", [
    {"complete": False},
    {"files": OBSERVED.files[:1]},
    {"files": OBSERVED.files + (OBSERVED.files[0],)},
    {"root_file_index": 201},
    {"root_volume_serial": 101},
])
def test_incomplete_or_identity_conflict_denied(change):
    with pytest.raises(PackageInventoryDenied):
        compare_package_inventory(EXPECTED, replace(OBSERVED, **change))


@pytest.mark.parametrize("change", [
    {"path": "tools/other.py"},
    {"path": "Tools/worker.py"},
    {"sha256": "c" * 64},
    {"size": 21},
    {"volume_serial": 101},
    {"file_index": 201},
    {"link_count": 2},
    {"reparse_point": True},
])
def test_observed_file_drift_denied(change):
    changed = replace(OBSERVED.files[1], **change)
    with pytest.raises(PackageInventoryDenied):
        compare_package_inventory(EXPECTED, replace(
            OBSERVED, files=(OBSERVED.files[0], changed),
        ))


@pytest.mark.parametrize("path", [
    "../app.py", "tools//worker.py", "tools\\worker.py",
    "C:/app.py", "tools/CON.txt", "tools/worker.py.",
    "tools/worker.py ", "tools/worker:alt.py", "tools/./worker.py",
])
def test_noncanonical_expected_path_denied(path):
    with pytest.raises(PackageInventoryDenied):
        compare_package_inventory((replace(EXPECTED[0], path=path),),
                                  replace(OBSERVED, files=OBSERVED.files[:1]))


def test_case_insensitive_expected_collision_denied():
    with pytest.raises(PackageInventoryDenied):
        compare_package_inventory((EXPECTED[0], replace(
            EXPECTED[0], path="APP.py",
        )), OBSERVED)


def test_extra_file_denied_even_when_expected_files_match():
    extra = ObservedPackageFile("extra.txt", "c" * 64, 1, 100, 203, 1, False)
    with pytest.raises(PackageInventoryDenied):
        compare_package_inventory(EXPECTED, replace(
            OBSERVED, files=OBSERVED.files + (extra,),
        ))
