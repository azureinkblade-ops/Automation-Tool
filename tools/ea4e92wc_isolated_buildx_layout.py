"""Value-only preflight for an isolated Docker CLI Buildx search layout."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
import re
import time


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REPARSE_POINT = 0x400


class LayoutDenied(ValueError):
    pass


@dataclass(frozen=True)
class IsolatedBuildxLayout:
    config_dir: Path
    program_files: Path
    plugin_sha256: str


def _plain(path: Path, *, directory: bool) -> bool:
    try:
        stat = path.lstat()
    except OSError:
        return False
    if getattr(stat, "st_file_attributes", 0) & _REPARSE_POINT:
        return False
    if path.is_symlink():
        return False
    return path.is_dir() if directory else path.is_file()


def _check_deadline(deadline: float | None, clock) -> None:
    if deadline is not None and clock() >= deadline:
        raise LayoutDenied("isolated plugin deadline reached")


def _plain_chain(path: Path, *, directory: bool, deadline: float | None,
                 clock) -> bool:
    _check_deadline(deadline, clock)
    if (not path.is_absolute() or not re.fullmatch(r"[A-Za-z]:", path.drive)
            or ".." in path.parts):
        return False
    try:
        if os.path.normcase(str(path.resolve(strict=True))) != os.path.normcase(str(path)):
            return False
    except OSError:
        return False
    for ancestor in path.parents:
        _check_deadline(deadline, clock)
        if not _plain(ancestor, directory=True):
            return False
    _check_deadline(deadline, clock)
    return _plain(path, directory=directory)


def _names(path: Path, *, deadline: float | None, clock) -> set[str]:
    unavailable = False
    try:
        names = set()
        _check_deadline(deadline, clock)
        for entry in path.iterdir():
            _check_deadline(deadline, clock)
            names.add(entry.name)
    except OSError:
        unavailable = True
    if unavailable:
        raise LayoutDenied("isolated plugin layout unavailable")
    return names


def _sha256(path: Path, *, deadline: float | None, clock) -> str:
    digest = hashlib.sha256()
    unavailable = False
    try:
        _check_deadline(deadline, clock)
        with path.open("rb") as stream:
            while True:
                _check_deadline(deadline, clock)
                chunk = stream.read(1024 * 1024)
                _check_deadline(deadline, clock)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        unavailable = True
    if unavailable:
        raise LayoutDenied("isolated plugin unavailable")
    return digest.hexdigest()


def isolated_environment(config_dir: Path, program_files: Path,
                         plugin_sha256: str, *, deadline: float | None = None,
                         clock=time.monotonic) -> dict[str, str]:
    """Verify a point-in-time layout; caller must still prove ACL and launch bounds."""
    _check_deadline(deadline, clock)
    if (os.path.normcase(os.environ.get("SYSTEMROOT", r"C:\Windows"))
            != os.path.normcase(r"C:\Windows")):
        raise LayoutDenied("isolated Windows root mismatch")
    if (type(plugin_sha256) is not str
            or _SHA256.fullmatch(plugin_sha256) is None
            or not config_dir.is_absolute() or not program_files.is_absolute()
            or config_dir == program_files):
        raise LayoutDenied("invalid isolated layout request")
    docker_dir = program_files / "Docker"
    plugin_dir = docker_dir / "cli-plugins"
    plugin = plugin_dir / "docker-buildx.exe"
    if (not all(_plain_chain(path, directory=True, deadline=deadline,
                             clock=clock) for path in (
            config_dir, program_files, docker_dir, plugin_dir))
            or not _plain_chain(plugin, directory=False, deadline=deadline,
                                clock=clock)
            or _names(config_dir, deadline=deadline, clock=clock)
            or _names(program_files, deadline=deadline, clock=clock) != {"Docker"}
            or _names(docker_dir, deadline=deadline, clock=clock) != {"cli-plugins"}
            or _names(plugin_dir, deadline=deadline, clock=clock) != {"docker-buildx.exe"}
            or _sha256(plugin, deadline=deadline, clock=clock) != plugin_sha256):
        raise LayoutDenied("isolated plugin layout mismatch")
    _check_deadline(deadline, clock)
    return {
        "SYSTEMROOT": r"C:\Windows",
        "DOCKER_CONFIG": str(config_dir),
        "ProgramFiles": str(program_files),
    }
