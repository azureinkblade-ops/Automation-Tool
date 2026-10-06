"""Fake-only staging tests; no container, receiver, or provider call."""

import hashlib
import inspect
from pathlib import Path

import pytest

from tools.hermes_core import local_kilo_inert_inputs as subject


def test_input_and_runtime_copies_are_distinct_and_hash_bound(tmp_path):
    result = subject.prepare_inert_inputs(tmp_path / "handoff")
    assert result["launch_authorized"] is False
    assert len(result["files"]) == 2
    for item in result["files"]:
        source = Path(item["input_path"])
        runtime = Path(item["runtime_path"])
        assert source != runtime
        assert source.read_bytes() == runtime.read_bytes()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item["sha256"]

    config = next(item for item in result["files"] if item["input_path"].endswith("kilo.jsonc"))
    runtime = Path(config["runtime_path"])
    source = Path(config["input_path"])
    runtime.write_bytes(b"runtime rewrite\n")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == config["sha256"]
    assert hashlib.sha256(runtime.read_bytes()).hexdigest() != config["sha256"]


def test_existing_root_is_rejected_without_overwriting(tmp_path):
    root = tmp_path / "handoff"
    root.mkdir()
    sentinel = root / "keep.txt"
    sentinel.write_text("unchanged", encoding="ascii")
    with pytest.raises(ValueError, match="root must be new"):
        subject.prepare_inert_inputs(root)
    assert sentinel.read_text(encoding="ascii") == "unchanged"


def test_corrupt_runtime_write_fails_closed(tmp_path, monkeypatch):
    original = Path.write_bytes

    def corrupt_runtime(path, content):
        if "runtime" in path.parts:
            content = b"unexpected bytes\n"
        return original(path, content)

    monkeypatch.setattr(Path, "write_bytes", corrupt_runtime)
    with pytest.raises(ValueError, match="staged input hash mismatch"):
        subject.prepare_inert_inputs(tmp_path / "corrupt")


def test_repo_path_is_rejected_without_creating_files():
    root = Path.cwd() / "ea4e92dp-never-create"
    assert not root.exists()
    with pytest.raises(ValueError, match="system temp directory"):
        subject.prepare_inert_inputs(root)
    assert not root.exists()


def test_materializer_has_no_container_or_network_capability():
    source = inspect.getsource(subject).lower()
    assert not any(name in source for name in ("subprocess", "requests", "socket", "popen", "exec("))
