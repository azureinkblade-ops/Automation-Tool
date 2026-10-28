"""Synthetic-only staged-context identity tests; no Docker or model."""

import hashlib
import io
from pathlib import Path
import tarfile

import pytest

import tools.ea4e92ux_context_consumer as consumer


def _staged_path(root: Path, monkeypatch, *, payload=b"synthetic") -> Path:
    name = "blobs/sha256-" + "a" * 64
    expected = ((name, hashlib.sha256(b"synthetic").hexdigest()),)
    monkeypatch.setattr(consumer, "EXPECTED_MODEL_FILES", expected)
    monkeypatch.setattr(consumer, "expected_recipe_bytes", lambda _: b"FROM synthetic\n")
    path = root / ("ea4e92ur-" + "a" * 32 + ".unverified.tar")
    with tarfile.open(path, "w") as archive:
        for member_name, data in (("Dockerfile", b"FROM synthetic\n"),
                                  (name, payload)):
            member = tarfile.TarInfo(member_name)
            member.size = len(data)
            member.mode = 0o444
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

    def redirected_open(candidate, *args, **kwargs):
        return original_open(replacement if candidate == path else candidate,
                             *args, **kwargs)

    monkeypatch.setattr(Path, "open", redirected_open)
    with pytest.raises(consumer.ContextDenied, match="identity mismatch"):
        with consumer.opened_staged_context(path, tmp_path):
            pytest.fail("used replacement")


def test_size_change_during_consumption_denied(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch)
    with pytest.raises(consumer.ContextDenied, match="changed during consumption"):
        with consumer.opened_staged_context(path, tmp_path):
            path.write_bytes(b"synthetic plus")


def test_hash_mismatch_denied_before_consumer(tmp_path, monkeypatch):
    path = _staged_path(tmp_path, monkeypatch, payload=b"tampered")
    with pytest.raises(consumer.ContextDenied, match="hash mismatch"):
        with consumer.opened_staged_context(path, tmp_path):
            pytest.fail("consumed tampered context")
