"""Value-only Docker build policy; no process, daemon, or model call."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from tools.ea4e92rm_container_smoke import LOCAL_DOCKER_HOST
from tools.ea4e92rq_nonmodel_probe import DOCKER, DOCKER_SHA256, IMAGE, IMAGE_ID


_CONTEXT = re.compile(r"ea4e92ur-([0-9a-f]{32})[.]unverified[.]tar")


@dataclass(frozen=True)
class BuildLaunchPolicy:
    docker_binary: Path
    docker_sha256: str
    base_image: str
    base_image_id: str
    context: Path
    iidfile: Path
    argv: tuple[str, ...]
    work_seconds: int
    wall_seconds: int
    output_bytes: int


def make_build_policy(context: Path, staging_dir: Path) -> BuildLaunchPolicy:
    """Freeze one local-only, no-push build request for later review.

    The caller must separately prove the private ACL, exact returned context
    identity, local builder driver, pre-start process limits, and cleanup.
    """
    if (not isinstance(staging_dir, Path) or not staging_dir.is_absolute()
            or staging_dir.is_symlink()
            or staging_dir.resolve(strict=True) != staging_dir
            or not staging_dir.is_dir()):
        raise ValueError("staging directory identity mismatch")
    if (not isinstance(context, Path) or not context.is_absolute()
            or context.parent != staging_dir or context.is_symlink()
            or context.resolve(strict=True) != context):
        raise ValueError("context path identity mismatch")
    match = _CONTEXT.fullmatch(context.name)
    if match is None:
        raise ValueError("unreviewed context name")
    iidfile = staging_dir / ("ea4e92vd-" + match.group(1) + ".iid")
    if iidfile.exists() or iidfile.is_symlink():
        raise ValueError("image-id output collision")
    argv = (
        str(DOCKER), "--host", LOCAL_DOCKER_HOST, "buildx", "build",
        "--builder=default", "--platform=linux/amd64", "--network=none",
        "--pull=false", "--no-cache", "--load", "--progress=quiet",
        "--iidfile", str(iidfile), "-",
    )
    return BuildLaunchPolicy(
        DOCKER, DOCKER_SHA256, IMAGE, IMAGE_ID, context, iidfile, argv,
        work_seconds=1800, wall_seconds=1860, output_bytes=1024 * 1024,
    )
