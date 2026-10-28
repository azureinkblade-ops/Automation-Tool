"""Minimal model-image build context stream; does not invoke Docker."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import re
import stat
import tarfile
from typing import BinaryIO

from tools.ea4e92rm_container_smoke import EXPECTED_MODEL_FILES
from tools.ea4e92sb_local_model_smoke import IMAGE


RECIPE = Path(__file__).with_name("ea4e92ul_model_image.Dockerfile")
MAX_CONTEXT_BYTES = 10 * 1024**3
CHUNK_BYTES = 1024 * 1024


class ContextDenied(RuntimeError):
    """The staged inputs or streamed bytes did not match the pinned recipe."""


class _HashingReader:
    def __init__(self, source: BinaryIO):
        self.source = source
        self.digest = hashlib.sha256()
        self.count = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise ContextDenied("unbounded model read denied")
        data = self.source.read(min(size, CHUNK_BYTES))
        self.digest.update(data)
        self.count += len(data)
        return data


def _member(name: str, size: int) -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.size = size
    member.mode = 0o444
    member.mtime = 0
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    return member


def expected_recipe_bytes(files: tuple[tuple[str, str], ...]) -> bytes:
    checks = " ".join(
        f"'{digest}  /models/{name}'" for name, digest in files
    )
    verification = (
        'RUN set -eu; test "$(find /models -type f | wc -l)" -eq 6; '
        'test -z "$(find /models -type l -print -quit)"; '
        "printf '%s\\n' " + checks + " | sha256sum -c -"
    )
    return ("\n".join([
        f"FROM {IMAGE}",
        *(f"COPY {name} /models/{name}" for name, _ in files),
        verification,
    ]) + "\n").encode("ascii")


def stream_context(root: Path, output: BinaryIO) -> None:
    """Write only pinned paths to a tar stream; caller aborts on any error."""
    if (not isinstance(root, Path) or not root.is_absolute()
            or root.is_symlink() or root.resolve(strict=True) != root
            or not root.is_dir()):
        raise ContextDenied("model root identity mismatch")
    files = EXPECTED_MODEL_FILES
    names = [name for name, _ in files]
    if (len(files) != 6 or len(set(names)) != 6
            or any(not re.fullmatch(r"(?:blobs/sha256-[0-9a-f]{64}|"
                                        r"manifests/registry[.]ollama[.]ai/"
                                        r"library/qwen3/14b)", name)
                   for name in names)
            or any(not re.fullmatch(r"[0-9a-f]{64}", digest)
                   for _, digest in files)):
        raise ContextDenied("reviewed model inventory invalid")
    expected_recipe = expected_recipe_bytes(files)
    if RECIPE.read_bytes().replace(b"\r\n", b"\n") != expected_recipe:
        raise ContextDenied("model image recipe mismatch")

    sources = []
    total = len(expected_recipe)
    for name, expected in files:
        candidate = root.joinpath(*name.split("/"))
        if (candidate.is_symlink() or candidate.resolve(strict=True) != candidate
                or not stat.S_ISREG(candidate.stat().st_mode)):
            raise ContextDenied("model file identity mismatch")
        size = candidate.stat().st_size
        if size < 0 or size > MAX_CONTEXT_BYTES - total:
            raise ContextDenied("model context size bound exceeded")
        total += size
        sources.append((name, expected, candidate, size))

    with tarfile.open(fileobj=output, mode="w|", format=tarfile.PAX_FORMAT) as archive:
        archive.addfile(_member("Dockerfile", len(expected_recipe)),
                        io.BytesIO(expected_recipe))
        for name, expected, candidate, size in sources:
            with candidate.open("rb") as source:
                opened = os.fstat(source.fileno())
                if not stat.S_ISREG(opened.st_mode) or opened.st_size != size:
                    raise ContextDenied("model file changed before stream")
                reader = _HashingReader(source)
                archive.addfile(_member(name, size), reader)
                if reader.count != size or reader.digest.hexdigest() != expected:
                    raise ContextDenied("streamed model bytes mismatch")
