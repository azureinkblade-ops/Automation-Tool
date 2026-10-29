"""Synthetic-only build-policy tests; never invoke Docker or read model bytes."""

import hashlib
import io
import os
from pathlib import Path
import tarfile

import pytest

import tools.ea4e92ux_context_consumer as consumer
import tools.ea4e92vd_build_launch_policy as policy_module


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows exclusive handle")


def _context(root: Path, monkeypatch) -> Path:
    names = [f"blobs/sha256-{index:064x}" for index in range(6)]
    files = tuple((name, hashlib.sha256(f"synthetic-{index}".encode()).hexdigest())
                  for index, name in enumerate(names))
    recipe = f"FROM {policy_module.IMAGE}\n".encode("ascii")
    monkeypatch.setattr(consumer, "EXPECTED_MODEL_FILES", files)
    monkeypatch.setattr(consumer, "expected_recipe_bytes", lambda _: recipe)
    monkeypatch.setattr(policy_module, "EXPECTED_MODEL_FILES", files)
    monkeypatch.setattr(policy_module, "expected_recipe_bytes", lambda _: recipe)
    recipe_path = root / "reviewed.Dockerfile"
    recipe_path.write_bytes(recipe)
    monkeypatch.setattr(policy_module, "RECIPE", recipe_path)
    path = root / ("ea4e92ur-" + "a" * 32 + ".unverified.tar")
    with tarfile.open(path, "w") as archive:
        for name, data in [("Dockerfile", recipe), *(
                (name, f"synthetic-{index}".encode())
                for index, name in enumerate(names))]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o444
            archive.addfile(member, io.BytesIO(data))
    return path


def test_policy_holds_verified_handle_and_freezes_no_push_args(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch)
    with policy_module.opened_build_policy(context, tmp_path) as policy:
        assert policy.context == context
        assert policy.source.read(6) == b"Docker"
        assert policy.argv[-1] == "-"
        assert policy.argv[1:3] == ("--host", "npipe:////./pipe/dockerDesktopLinuxEngine")
        assert "--network=none" in policy.argv
        assert "--pull=false" in policy.argv
        assert "--no-cache" in policy.argv
        assert "--load" in policy.argv
        assert "--quiet" in policy.argv
        assert "--push" not in policy.argv
        assert "--iidfile" not in policy.argv
        assert "--metadata-file" not in policy.argv
        assert not hasattr(policy, "iidfile")
        assert policy.work_seconds < policy.wall_seconds
    assert policy.source.closed


def test_same_named_non_archive_and_directory_denied(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch)
    context.write_bytes(b"synthetic")
    with pytest.raises(consumer.ContextDenied):
        with policy_module.opened_build_policy(context, tmp_path):
            pytest.fail("accepted unverified archive")
    directory_root = tmp_path / "directory"
    directory_root.mkdir()
    directory = directory_root / context.name
    directory.mkdir()
    with pytest.raises(consumer.ContextDenied):
        with policy_module.opened_build_policy(directory, directory_root):
            pytest.fail("accepted directory")


def test_wrong_directory_and_name_denied(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(consumer.ContextDenied):
        with policy_module.opened_build_policy(context, other):
            pytest.fail("accepted wrong directory")
    wrong = tmp_path / "unreviewed.tar"
    wrong.write_bytes(b"synthetic")
    with pytest.raises(consumer.ContextDenied):
        with policy_module.opened_build_policy(wrong, tmp_path):
            pytest.fail("accepted wrong name")


def test_recipe_pin_mismatch_denied_before_context_open(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch)
    policy_module.RECIPE.write_bytes(b"FROM other\n")
    with pytest.raises(ValueError, match="recipe mismatch"):
        with policy_module.opened_build_policy(context, tmp_path):
            pytest.fail("accepted changed recipe")


def test_preexisting_image_id_file_is_not_used_or_changed(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch)
    iidfile = tmp_path / ("ea4e92vd-" + "a" * 32 + ".iid")
    iidfile.write_text("existing", encoding="ascii")
    with policy_module.opened_build_policy(context, tmp_path) as policy:
        assert str(iidfile) not in policy.argv
        assert policy.argv[-2:] == ("--quiet", "-")
    assert iidfile.read_text(encoding="ascii") == "existing"


@pytest.mark.parametrize("suffix", [b"", b"\n", b"\r\n"])
def test_quiet_image_id_accepts_one_canonical_digest(suffix):
    identity = b"sha256:" + b"a" * 64
    assert policy_module.parse_quiet_image_id(identity + suffix) == identity.decode("ascii")


@pytest.mark.parametrize("output", [
    b"", b"a" * 64, b"sha256:" + b"A" * 64,
    b"sha256:" + b"a" * 63, b"sha256:" + b"a" * 65,
    b"sha256:" + b"a" * 64 + b"\nextra",
    b" sha256:" + b"a" * 64, b"sha256:" + b"a" * 64 + b" ",
    b"\xff" + b"a" * 70, b"x" * 129,
])
def test_quiet_image_id_rejects_extra_or_malformed_output(output):
    with pytest.raises(ValueError, match="image ID invalid"):
        policy_module.parse_quiet_image_id(output)


def test_quiet_image_id_rejects_non_bytes():
    with pytest.raises(ValueError, match="image ID invalid"):
        policy_module.parse_quiet_image_id("sha256:" + "a" * 64)
