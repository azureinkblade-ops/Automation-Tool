"""Read-only native closure-walk candidate against disposable fixtures only."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("package-closure-walk") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPathTopologyCandidate.cs"),
         str(ROOT / "tools" / "Ea4eProtectedByteSnapshotCandidate.cs"),
         str(ROOT / "tools" / "Ea4ePackageClosureWalkCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92mg_package_closure_walk_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check(executable, root, *entries):
    arguments = [str(executable), str(root)]
    for path, content in entries:
        arguments.extend((path, digest(content)))
    return subprocess.run(arguments, capture_output=True, text=True,
                          timeout=10, check=False)


def package(tmp_path, *, worker=True):
    root = tmp_path / "package"
    (root / "tools").mkdir(parents=True)
    (root / "app.py").write_bytes(b"app")
    if worker:
        (root / "tools" / "worker.py").write_bytes(b"worker")
    return root


def test_exact_file_set_is_only_an_unprotected_walk(executable, tmp_path):
    root = package(tmp_path)
    result = check(executable, root, ("app.py", b"app"),
                   ("tools/worker.py", b"worker"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:UNPROTECTED_WALK_ONLY"


def test_missing_expected_file_denied(executable, tmp_path):
    root = package(tmp_path, worker=False)
    result = check(executable, root, ("app.py", b"app"),
                   ("tools/worker.py", b"worker"))
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:EXPECTED_FILE_MISSING"


@pytest.mark.parametrize("extra", ["file", "directory"])
def test_unexpected_entry_denied(executable, tmp_path, extra):
    root = package(tmp_path)
    if extra == "file":
        (root / "extra.txt").write_bytes(b"extra")
    else:
        (root / "extra").mkdir()
    result = check(executable, root, ("app.py", b"app"),
                   ("tools/worker.py", b"worker"))
    assert result.returncode == 1
    assert result.stdout.strip() == (
        "DENY:UNEXPECTED_OR_DUPLICATE_FILE" if extra == "file"
        else "DENY:UNEXPECTED_DIRECTORY"
    )


def test_changed_file_bytes_denied(executable, tmp_path):
    root = package(tmp_path)
    result = check(executable, root, ("app.py", b"old"),
                   ("tools/worker.py", b"worker"))
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:BYTE_HASH_MISMATCH"


@pytest.mark.parametrize("bad", ["../app.py", "tools\\worker.py", "CON.txt"])
def test_bad_manifest_path_denied(executable, tmp_path, bad):
    root = package(tmp_path)
    result = check(executable, root, (bad, b"app"))
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:EXPECTED_MANIFEST_INVALID"


def test_file_directory_manifest_collision_denied(executable, tmp_path):
    root = package(tmp_path)
    result = check(executable, root, ("tools", b"file"),
                   ("tools/worker.py", b"worker"))
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:EXPECTED_MANIFEST_INVALID"


def test_file_cannot_be_package_root(executable, tmp_path):
    root = package(tmp_path)
    result = check(executable, root / "app.py", ("app.py", b"app"))
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:OBJECT_TYPE_DENIED"


def test_hardlinked_file_denied(executable, tmp_path):
    root = package(tmp_path)
    try:
        os.link(root / "app.py", tmp_path / "other.py")
    except OSError as error:
        pytest.skip(f"Hard links unavailable: {error}")
    result = check(executable, root, ("app.py", b"app"),
                   ("tools/worker.py", b"worker"))
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:MULTILINK_DENIED"


def test_symlinked_directory_denied(executable, tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    (root / "app.py").write_bytes(b"app")
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "worker.py").write_bytes(b"worker")
    try:
        os.symlink(target, root / "tools", target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks unavailable: {error}")
    result = check(executable, root, ("app.py", b"app"),
                   ("tools/worker.py", b"worker"))
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:REPARSE_DENIED"
