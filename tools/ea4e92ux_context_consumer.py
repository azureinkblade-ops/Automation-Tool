"""Source-only guard for a staged model build context; never invokes Docker."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import stat
import tarfile
from typing import BinaryIO, Iterator

from tools.ea4e92rm_container_smoke import EXPECTED_MODEL_FILES
from tools.ea4e92um_model_build_context import ContextDenied, expected_recipe_bytes
from tools.ea4e92ur_staged_build_context import MAX_TAR_BYTES


_STAGED_NAME = re.compile(r"ea4e92ur-[0-9a-f]{32}[.]unverified[.]tar")
CHUNK_BYTES = 1024 * 1024


def _verify_tar(source: BinaryIO) -> None:
    recipe = expected_recipe_bytes(EXPECTED_MODEL_FILES)
    expected = [("Dockerfile", None), *EXPECTED_MODEL_FILES]
    count = 0
    try:
        with tarfile.open(fileobj=source, mode="r|") as archive:
            for member in archive:
                if count >= len(expected):
                    raise ContextDenied("staged context inventory mismatch")
                name, digest = expected[count]
                if (member.name != name or not member.isfile()
                        or member.size < 0 or member.size > MAX_TAR_BYTES
                        or member.mode != 0o444 or member.uid != 0
                        or member.gid != 0 or member.mtime != 0):
                    raise ContextDenied("staged context member mismatch")
                content = archive.extractfile(member)
                if content is None:
                    raise ContextDenied("staged context member unreadable")
                hasher = hashlib.sha256()
                size = 0
                while chunk := content.read(CHUNK_BYTES):
                    size += len(chunk)
                    if size > member.size:
                        raise ContextDenied("staged context member size mismatch")
                    hasher.update(chunk)
                    if count == 0 and (size > len(recipe)
                                       or chunk != recipe[size - len(chunk):size]):
                        raise ContextDenied("staged context recipe mismatch")
                if size != member.size or (count == 0 and size != len(recipe)):
                    raise ContextDenied("staged context member size mismatch")
                if digest is not None and hasher.hexdigest() != digest:
                    raise ContextDenied("staged context hash mismatch")
                count += 1
    except (tarfile.TarError, OSError, EOFError) as error:
        raise ContextDenied("staged context tar invalid") from None
    if count != len(expected):
        raise ContextDenied("staged context inventory mismatch")
    source.seek(0)


@contextmanager
def opened_staged_context(path: Path, staging_dir: Path) -> Iterator[BinaryIO]:
    """Hold one verified file identity open for a future bounded consumer.

    The caller must use this exact handle, not reopen the path or scan a
    directory. This does not establish ACL privacy or immutable file bytes.
    """
    if (not isinstance(staging_dir, Path) or not staging_dir.is_absolute()
            or staging_dir.is_symlink()
            or staging_dir.resolve(strict=True) != staging_dir
            or not staging_dir.is_dir()):
        raise ContextDenied("staging directory identity mismatch")
    if (not isinstance(path, Path) or not path.is_absolute()
            or not _STAGED_NAME.fullmatch(path.name)
            or path.parent != staging_dir
            or path.is_symlink() or path.resolve(strict=True) != path):
        raise ContextDenied("staged context path mismatch")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_TAR_BYTES:
        raise ContextDenied("staged context file bound failed")
    with path.open("rb") as source:
        opened = os.fstat(source.fileno())
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino, opened.st_size)
                != (before.st_dev, before.st_ino, before.st_size)):
            raise ContextDenied("staged context identity mismatch")
        _verify_tar(source)
        yield source
        after = os.fstat(source.fileno())
        if (after.st_dev, after.st_ino, after.st_size) != (
                opened.st_dev, opened.st_ino, opened.st_size):
            raise ContextDenied("staged context changed during consumption")
