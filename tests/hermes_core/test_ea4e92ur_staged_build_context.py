"""Synthetic-only staged-context tests; no Docker or model is invoked."""

import io
from pathlib import Path
import tarfile

import pytest

import tools.ea4e92ur_staged_build_context as staged


def test_complete_stream_exposes_only_ready_tar(tmp_path, monkeypatch):
    def fake_stream(_root, output):
        with tarfile.open(fileobj=output, mode="w|") as archive:
            item = tarfile.TarInfo("synthetic")
            item.size = 3
            archive.addfile(item, io.BytesIO(b"abc"))

    monkeypatch.setattr(staged, "stream_context", fake_stream)
    ready = staged.stage_context(tmp_path, tmp_path)
    assert ready.name.endswith(".ready.tar")
    assert not list(tmp_path.glob("*.partial"))
    with tarfile.open(ready, "r:") as archive:
        assert archive.extractfile("synthetic").read() == b"abc"


def test_failed_stream_keeps_partial_but_never_exposes_ready(tmp_path, monkeypatch):
    def failing_stream(_root, output):
        output.write(b"partial synthetic bytes")
        raise staged.ContextDenied("synthetic failure")

    monkeypatch.setattr(staged, "stream_context", failing_stream)
    with pytest.raises(staged.ContextDenied, match="synthetic failure"):
        staged.stage_context(tmp_path, tmp_path)
    assert len(list(tmp_path.glob("*.partial"))) == 1
    assert not list(tmp_path.glob("*.ready.tar"))


def test_noncanonical_staging_directory_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(staged, "stream_context", lambda *_: pytest.fail("streamed"))
    with pytest.raises(staged.ContextDenied, match="staging directory"):
        staged.stage_context(tmp_path, Path("relative"))
