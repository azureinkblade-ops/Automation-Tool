"""Stage a verified model context without invoking Docker or a model."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from tools.ea4e92um_model_build_context import ContextDenied, MAX_CONTEXT_BYTES, stream_context


MAX_TAR_BYTES = MAX_CONTEXT_BYTES + 1024 * 1024


class _BoundedOutput:
    def __init__(self, output):
        self.output = output
        self.count = 0

    def write(self, data):
        if len(data) > MAX_TAR_BYTES - self.count:
            raise ContextDenied("staged context size bound exceeded")
        written = self.output.write(data)
        self.count += written
        return written


def stage_context(root: Path, staging_dir: Path) -> Path:
    """Return a staged path only after a complete, synced stream.

    A failed write leaves its uniquely named file for reconciliation. Only
    the returned path, never a path discovered by directory scan, is usable.
    """
    if (not isinstance(staging_dir, Path) or not staging_dir.is_absolute()
            or staging_dir.is_symlink()
            or staging_dir.resolve(strict=True) != staging_dir
            or not staging_dir.is_dir()):
        raise ContextDenied("staging directory identity mismatch")

    stem = "ea4e92ur-" + uuid4().hex
    if not re.fullmatch(r"ea4e92ur-[0-9a-f]{32}", stem):
        raise ContextDenied("staging identity invalid")
    staged = staging_dir / (stem + ".unverified.tar")
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as output:
        stream_context(root, _BoundedOutput(output))
        output.flush()
        os.fsync(output.fileno())
        written = os.fstat(output.fileno())

    opened = staged.stat()
    if (not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_TAR_BYTES
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (written.st_dev, written.st_ino, written.st_size)):
        raise ContextDenied("staged context identity mismatch")
    return staged
