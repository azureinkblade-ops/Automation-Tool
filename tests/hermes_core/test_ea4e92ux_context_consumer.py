"""Synthetic-only staged-context identity tests; no Docker or model."""

import hashlib
import io
import os
from pathlib import Path
import tarfile

import pytest

import tools.ea4e92ux_context_consumer as consumer
import tools.ea4e92um_model_build_context as context_writer

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows exclusive handle")


def _staged_path(root: Path, monkeypatch, *, payload=b"synthetic",
                 recipe=b"FROM synthetic\n", mode=0o444) -> Path:
    names = [f"blobs/sha256-{index:064x}" for index in range(6)]
    expected = tuple((name, hashlib.sha256(f"synthetic-{index}".encode()).hexdigest())
                     for index, name in enumerate(names))
    monkeypatch.setattr(consumer, "EXPECTED_MODEL_FILES", expected)
    monkeypatch.setattr(consumer, "expected_recipe_bytes", lambda _: b"FROM synthetic\n")
    path = root / ("ea4e92ur-" + "a" * 32 + ".unverified.tar")
    with tarfile.open(path, "w") as archive:
        members = [("Dockerfile", recipe)]
        members.extend((name, payload if index == 0 and payload != b"synthetic"
                        else f"synthetic-{index}".encode())
                       for index, name in enumerate(names))
        for member_name, data in members:
            member = tarfile.TarInfo(member_name)
            member.size = len(data)
            member.mode = mode
            archive.addfile(member, io.BytesIO(data))
    return path


def test_consumer_holds_exact_file_handle(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch)
    with consumer.opened_staged_context(path, tmp_path) as source:
        assert source.read(6) == b"Docker"


def test_wrong_directory_denied(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(consumer.ContextDenied, match="path mismatch"):
        with consumer.opened_staged_context(path, other):
            pytest.fail("opened wrong directory")


def test_replaced_open_handle_denied(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"x" * path.stat().st_size)
    original_open = Path.open

    def redirected_open(_candidate):
        return original_open(replacement, "rb")

    monkeypatch.setattr(consumer, "_open_without_writers", redirected_open)
    with pytest.raises(consumer.ContextDenied, match="identity mismatch"):
        with consumer.opened_staged_context(path, tmp_path):
            pytest.fail("used replacement")


def test_same_size_write_denied_while_handle_open(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch)
    with consumer.opened_staged_context(path, tmp_path):
        with pytest.raises(OSError):
            with path.open("r+b") as writer:
                writer.write(b"X")


def test_hash_mismatch_denied_before_consumer(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch, payload=b"tampered")
    with pytest.raises(consumer.ContextDenied, match="hash mismatch"):
        with consumer.opened_staged_context(path, tmp_path):
            pytest.fail("consumed tampered context")


@pytest.mark.parametrize("change", ["extra", "truncated"])
def test_archive_framing_denied(tmp_path, monkeypatch, change):
    path = _staged_path(tmp_path, monkeypatch)
    if change == "extra":
        with path.open("ab") as output:
            output.write(b"extra archive bytes")
    else:
        with path.open("r+b") as output:
            output.truncate(path.stat().st_size - 1)
    with pytest.raises(consumer.ContextDenied):
        with consumer.opened_staged_context(path, tmp_path):
            pytest.fail("consumed malformed tar")


def test_recipe_mismatch_denied(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch, recipe=b"FROM changed\n")
    with pytest.raises(consumer.ContextDenied, match="recipe mismatch"):
        with consumer.opened_staged_context(path, tmp_path):
            pytest.fail("consumed wrong Dockerfile")


def test_metadata_mismatch_denied(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch, mode=0o600)
    with pytest.raises(consumer.ContextDenied, match="member mismatch"):
        with consumer.opened_staged_context(path, tmp_path):
            pytest.fail("consumed wrong metadata")


def test_caller_error_still_closes_handle(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="caller failure"):
        with consumer.opened_staged_context(path, tmp_path):
            raise RuntimeError("caller failure")
    with path.open("r+b") as writer:
        writer.write(b"X")


def test_real_context_writer_format_with_synthetic_files(tmp_path, monkeypatch):
    root = tmp_path / "model"
    staging = tmp_path / "staging"
    staging.mkdir()
    names = ["manifests/registry.ollama.ai/library/qwen3/14b"]
    names += [f"blobs/sha256-{index:064x}" for index in range(5)]
    expected = []
    for index, name in enumerate(names):
        path = root.joinpath(*name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"synthetic-{index}".encode()
        path.write_bytes(payload)
        expected.append((name, hashlib.sha256(payload).hexdigest()))
    expected = tuple(expected)
    recipe = tmp_path / "Dockerfile"
    recipe.write_bytes(context_writer.expected_recipe_bytes(expected))
    monkeypatch.setattr(context_writer, "RECIPE", recipe)
    monkeypatch.setattr(context_writer, "EXPECTED_MODEL_FILES", expected)
    monkeypatch.setattr(consumer, "EXPECTED_MODEL_FILES", expected)
    staged = staging / ("ea4e92ur-" + "b" * 32 + ".unverified.tar")
    with staged.open("wb") as output:
        context_writer.stream_context(root, output)
    with consumer.opened_staged_context(staged, staging) as source:
        assert source.read(10) == b"Dockerfile"
