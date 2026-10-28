"""Value-only build-policy tests; never invoke Docker or read model bytes."""

from pathlib import Path

import pytest

from tools.ea4e92vd_build_launch_policy import make_build_policy


def _context(staging: Path) -> Path:
    path = staging / ("ea4e92ur-" + "a" * 32 + ".unverified.tar")
    path.write_bytes(b"synthetic")
    return path


def test_policy_freezes_local_no_push_arguments(tmp_path):
    context = _context(tmp_path)
    policy = make_build_policy(context, tmp_path)
    assert policy.context == context
    assert policy.argv[-1] == "-"
    assert policy.argv[1:3] == ("--host", "npipe:////./pipe/dockerDesktopLinuxEngine")
    assert "--network=none" in policy.argv
    assert "--pull=false" in policy.argv
    assert "--no-cache" in policy.argv
    assert "--load" in policy.argv
    assert "--push" not in policy.argv
    assert "--iidfile" in policy.argv
    assert policy.iidfile.parent == tmp_path
    assert policy.work_seconds < policy.wall_seconds


def test_wrong_directory_and_name_are_denied(tmp_path):
    context = _context(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="context path"):
        make_build_policy(context, other)
    wrong = tmp_path / "unreviewed.tar"
    wrong.write_bytes(b"synthetic")
    with pytest.raises(ValueError, match="context name"):
        make_build_policy(wrong, tmp_path)


def test_existing_iidfile_is_never_overwritten(tmp_path):
    context = _context(tmp_path)
    iidfile = tmp_path / ("ea4e92vd-" + "a" * 32 + ".iid")
    iidfile.write_text("existing", encoding="ascii")
    with pytest.raises(ValueError, match="collision"):
        make_build_policy(context, tmp_path)
    assert iidfile.read_text(encoding="ascii") == "existing"
