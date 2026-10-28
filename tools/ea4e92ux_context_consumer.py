"""Source-only guard for a staged model build context; never invokes Docker."""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
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
TAR_BLOCK = 512
TAR_RECORD = 10240


def _open_without_writers(path: Path) -> BinaryIO:
    if os.name != "nt":
        raise ContextDenied("exclusive staged context open unavailable")
    import msvcrt

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                            wintypes.HANDLE)
    create_file.restype = wintypes.HANDLE
    handle = create_file(str(path), 0x80000000, 0x00000001, None, 3,
                         0x08000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ContextDenied("exclusive staged context open denied")
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        ctypes.windll.kernel32.CloseHandle(handle)
        raise ContextDenied("exclusive staged context open denied") from None
    try:
        return os.fdopen(descriptor, "rb")
    except Exception:
        os.close(descriptor)
        raise ContextDenied("exclusive staged context open denied") from None


def _verify_tar(source: BinaryIO) -> None:
    recipe = expected_recipe_bytes(EXPECTED_MODEL_FILES)
    expected = [("Dockerfile", None), *EXPECTED_MODEL_FILES]
    count = 0
    padding = []
    try:
        with tarfile.open(fileobj=source, mode="r|") as archive:
            for member in archive:
                if count >= len(expected):
                    raise ContextDenied("staged context inventory mismatch")
                name, digest = expected[count]
                if (member.name != name or not member.isfile()
                        or member.size < 0 or member.size > MAX_TAR_BYTES
                        or member.mode != 0o444 or member.uid != 0
                        or member.gid != 0 or member.mtime != 0
                        or member.uname or member.gname):
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
                end = member.offset_data + member.size
                padded_end = ((end + TAR_BLOCK - 1) // TAR_BLOCK) * TAR_BLOCK
                padding.append((end, padded_end))
                count += 1
    except (tarfile.TarError, OSError, EOFError):
        raise ContextDenied("staged context tar invalid") from None
    if count != len(expected):
        raise ContextDenied("staged context inventory mismatch")
    total = os.fstat(source.fileno()).st_size
    if total % TAR_RECORD or total - padding[-1][1] < 2 * TAR_BLOCK:
        raise ContextDenied("staged context framing mismatch")
    for start, end in padding:
        source.seek(start)
        if any(source.read(end - start)):
            raise ContextDenied("staged context padding mismatch")
    source.seek(padding[-1][1])
    while chunk := source.read(CHUNK_BYTES):
        if any(chunk):
            raise ContextDenied("staged context trailing bytes")
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
    with _open_without_writers(path) as source:
        opened = os.fstat(source.fileno())
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino, opened.st_size)
                != (before.st_dev, before.st_ino, before.st_size)):
            raise ContextDenied("staged context identity mismatch")
        _verify_tar(source)
        try:
            yield source
        finally:
            after = os.fstat(source.fileno())
            if (after.st_dev, after.st_ino, after.st_size) != (
                    opened.st_dev, opened.st_ino, opened.st_size):
                raise ContextDenied("staged context changed during consumption")
