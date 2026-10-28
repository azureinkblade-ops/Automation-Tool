"""Fake-only minimal-context tests; no Docker or real model is invoked."""

import hashlib
import io
from pathlib import Path
import tarfile

import pytest

import tools.ea4e92um_model_build_context as context


def synthetic_stage(tmp_path: Path, monkeypatch):
    root = tmp_path / "model"
    names = ["manifests/registry.ollama.ai/library/qwen3/14b"]
    names += [f"blobs/sha256-{index:064x}" for index in range(5)]
    expected = []
    for index, name in enumerate(names):
        source = root.joinpath(*name.split("/"))
        source.parent.mkdir(parents=True, exist_ok=True)
        payload = (f"synthetic-{index}" * 100).encode("ascii")
        source.write_bytes(payload)
        expected.append((name, hashlib.sha256(payload).hexdigest()))
    recipe = tmp_path / "Dockerfile"
    recipe.write_bytes(context.expected_recipe_bytes(tuple(expected)))
    monkeypatch.setattr(context, "EXPECTED_MODEL_FILES", tuple(expected))
    monkeypatch.setattr(context, "RECIPE", recipe)
    return root, expected, recipe


def test_context_contains_only_recipe_and_six_pinned_files(tmp_path, monkeypatch):
    root, expected, recipe = synthetic_stage(tmp_path, monkeypatch)
    (root / "unrelated-private-file").write_bytes(b"must not enter context")
    output = io.BytesIO()
    context.stream_context(root, output)
    output.seek(0)
    with tarfile.open(fileobj=output, mode="r:") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == [
            "Dockerfile", *(name for name, _ in expected)]
        assert all(member.uid == member.gid == member.mtime == 0
                   and member.mode == 0o444 for member in members)
        assert archive.extractfile(members[0]).read() == recipe.read_bytes()
        for member, (_, digest) in zip(members[1:], expected):
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest() == digest
    assert b"must not enter context" not in output.getvalue()


def test_drifted_model_bytes_are_denied(tmp_path, monkeypatch):
    root, expected, _ = synthetic_stage(tmp_path, monkeypatch)
    root.joinpath(*expected[2][0].split("/")).write_bytes(b"changed")
    with pytest.raises(context.ContextDenied, match="streamed model bytes mismatch"):
        context.stream_context(root, io.BytesIO())


def test_crlf_checkout_streams_normalized_recipe(tmp_path, monkeypatch):
    root, _, recipe = synthetic_stage(tmp_path, monkeypatch)
    recipe.write_bytes(recipe.read_bytes().replace(b"\n", b"\r\n"))
    output = io.BytesIO()
    context.stream_context(root, output)
    output.seek(0)
    with tarfile.open(fileobj=output, mode="r:") as archive:
        assert archive.extractfile("Dockerfile").read().count(b"\r") == 0


def test_recipe_drift_denied_before_stream(tmp_path, monkeypatch):
    root, _, recipe = synthetic_stage(tmp_path, monkeypatch)
    recipe.write_bytes(recipe.read_bytes() + b"RUN echo unsafe\n")
    output = io.BytesIO()
    with pytest.raises(context.ContextDenied, match="recipe mismatch"):
        context.stream_context(root, output)
    assert not output.getvalue()


def test_total_size_bound_denied_before_stream(tmp_path, monkeypatch):
    root, _, _ = synthetic_stage(tmp_path, monkeypatch)
    monkeypatch.setattr(context, "MAX_CONTEXT_BYTES", 1)
    output = io.BytesIO()
    with pytest.raises(context.ContextDenied, match="size bound exceeded"):
        context.stream_context(root, output)
    assert not output.getvalue()
