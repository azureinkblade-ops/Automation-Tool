"""Value-only Docker build policy; no process, daemon, or model call."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from typing import BinaryIO, Iterator

from tools.ea4e92rm_container_smoke import EXPECTED_MODEL_FILES, LOCAL_DOCKER_HOST
from tools.ea4e92rq_nonmodel_probe import DOCKER, DOCKER_SHA256, IMAGE, IMAGE_ID
from tools.ea4e92um_model_build_context import RECIPE, expected_recipe_bytes
from tools.ea4e92ux_context_consumer import opened_staged_context


_CONTEXT = re.compile(r"ea4e92ur-([0-9a-f]{32})[.]unverified[.]tar")


@dataclass(frozen=True)
class BuildLaunchPolicy:
    docker_binary: Path
    docker_sha256: str
    base_image: str
    base_image_id: str
    context: Path
    source: BinaryIO
    iidfile: Path
    argv: tuple[str, ...]
    work_seconds: int
    wall_seconds: int
    output_bytes: int


def _make_build_policy(context: Path, staging_dir: Path,
                       source: BinaryIO) -> BuildLaunchPolicy:
    """Freeze arguments around the already verified, still-open archive.

    The caller must separately prove the private ACL, exact returned context
    identity, local builder driver, pre-start process limits, and cleanup.
    """
    if source.closed or not source.readable():
        raise ValueError("verified source handle required")
    opened = os.fstat(source.fileno())
    current = context.stat()
    if (not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (current.st_dev, current.st_ino, current.st_size)):
        raise ValueError("verified source identity mismatch")
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
        DOCKER, DOCKER_SHA256, IMAGE, IMAGE_ID, context, source, iidfile, argv,
        work_seconds=1800, wall_seconds=1860, output_bytes=1024 * 1024,
    )


@contextmanager
def opened_build_policy(context: Path, staging_dir: Path) -> Iterator[BuildLaunchPolicy]:
    """Hold the verified archive handle for a future bounded build transport.

    The output-path check is not an exclusive reservation. No process or
    daemon action is authorized by this source-only policy.
    """
    recipe = expected_recipe_bytes(EXPECTED_MODEL_FILES)
    if (not recipe.startswith(f"FROM {IMAGE}\n".encode("ascii"))
            or RECIPE.read_bytes().replace(b"\r\n", b"\n") != recipe):
        raise ValueError("base image recipe mismatch")
    with opened_staged_context(context, staging_dir) as source:
        yield _make_build_policy(context, staging_dir, source)
