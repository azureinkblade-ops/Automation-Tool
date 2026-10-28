"""Synthetic-only staged-context tests; no Docker or model is invoked."""

import io
from pathlib import Path
import tarfile

import pytest

import tools.ea4e92ur_staged_build_context as staged


def test_complete_stream_returns_exclusive_staged_tar(tmp_path, monkeypatch):
    def fake_stream(_root, output):
        with tarfile.open(fileobj=output, mode="w|") as archive:
            item = tarfile.TarInfo("synthetic")
            item.size = 3
            archive.addfile(item, io.BytesIO(b"abc"))

    monkeypatch.setattr(staged, "stream_context", fake_stream)
    result = staged.stage_context(tmp_path, tmp_path)
    assert result.name.endswith(".unverified.tar")
    assert len(list(tmp_path.glob("*.unverified.tar"))) == 1
    with tarfile.open(result, "r:") as archive:
        assert archive.extractfile("synthetic").read() == b"abc"


def test_failed_stream_keeps_partial_but_returns_no_path(tmp_path, monkeypatch):
    def failing_stream(_root, output):
        output.write(b"partial synthetic bytes")
        raise staged.ContextDenied("synthetic failure")

    monkeypatch.setattr(staged, "stream_context", failing_stream)
    with pytest.raises(staged.ContextDenied, match="synthetic failure"):
        staged.stage_context(tmp_path, tmp_path)
    assert len(list(tmp_path.glob("*.unverified.tar"))) == 1


def test_size_bound_denies_before_excess_bytes_are_written(tmp_path, monkeypatch):
    monkeypatch.setattr(staged, "MAX_TAR_BYTES", 8)

    def too_large(_root, output):
        output.write(b"1234")
        output.write(b"56789")

    monkeypatch.setattr(staged, "stream_context", too_large)
    with pytest.raises(staged.ContextDenied, match="size bound exceeded"):
        staged.stage_context(tmp_path, tmp_path)
    retained = list(tmp_path.glob("*.unverified.tar"))
    assert len(retained) == 1
    assert retained[0].read_bytes() == b"1234"


def test_noncanonical_staging_directory_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(staged, "stream_context", lambda *_: pytest.fail("streamed"))
    with pytest.raises(staged.ContextDenied, match="staging directory"):
        staged.stage_context(tmp_path, Path("relative"))
