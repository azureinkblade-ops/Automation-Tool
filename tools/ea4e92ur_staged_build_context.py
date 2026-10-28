"""Stage a verified model context without invoking Docker or a model."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from tools.ea4e92um_model_build_context import ContextDenied, MAX_CONTEXT_BYTES, stream_context


MAX_TAR_BYTES = MAX_CONTEXT_BYTES + 1024 * 1024


def stage_context(root: Path, staging_dir: Path) -> Path:
    """Return a ready tar path only after a complete, durable stream.

    A failed write deliberately leaves its uniquely named partial file for
    operator reconciliation; callers must never send partial files to Docker.
    """
    if (not isinstance(staging_dir, Path) or not staging_dir.is_absolute()
            or staging_dir.is_symlink()
            or staging_dir.resolve(strict=True) != staging_dir
            or not staging_dir.is_dir()):
        raise ContextDenied("staging directory identity mismatch")

    stem = "ea4e92ur-" + uuid4().hex
    if not re.fullmatch(r"ea4e92ur-[0-9a-f]{32}", stem):
        raise ContextDenied("staging identity invalid")
    partial = staging_dir / (stem + ".partial")
    ready = staging_dir / (stem + ".ready.tar")
    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as output:
        stream_context(root, output)
        output.flush()
        os.fsync(output.fileno())
        if output.tell() > MAX_TAR_BYTES:
            raise ContextDenied("staged context size bound exceeded")
        written = os.fstat(output.fileno())

    opened = partial.stat()
    if (not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_TAR_BYTES
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (written.st_dev, written.st_ino, written.st_size)):
        raise ContextDenied("staged context identity mismatch")
    if ready.exists() or ready.is_symlink():
        raise ContextDenied("ready context collision")
    os.rename(partial, ready)
    return ready
