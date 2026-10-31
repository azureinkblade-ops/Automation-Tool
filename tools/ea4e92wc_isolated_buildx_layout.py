"""Value-only preflight for an isolated Docker CLI Buildx search layout."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
import re


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


def _plain_chain(path: Path, *, directory: bool) -> bool:
    if (not path.is_absolute() or not re.fullmatch(r"[A-Za-z]:", path.drive)
            or ".." in path.parts):
        return False
    try:
        if os.path.normcase(str(path.resolve(strict=True))) != os.path.normcase(str(path)):
            return False
    except OSError:
        return False
    for ancestor in path.parents:
        if not _plain(ancestor, directory=True):
            return False
    return _plain(path, directory=directory)


def _names(path: Path) -> set[str]:
    try:
        return {entry.name for entry in path.iterdir()}
    except OSError:
        raise LayoutDenied("isolated plugin layout unavailable") from None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        raise LayoutDenied("isolated plugin unavailable") from None
    return digest.hexdigest()


def isolated_environment(config_dir: Path, program_files: Path,
                         plugin_sha256: str) -> dict[str, str]:
    """Verify a point-in-time layout; caller must still prove ACL and launch bounds."""
    if (type(plugin_sha256) is not str
            or _SHA256.fullmatch(plugin_sha256) is None
            or not config_dir.is_absolute() or not program_files.is_absolute()
            or config_dir == program_files):
        raise LayoutDenied("invalid isolated layout request")
    docker_dir = program_files / "Docker"
    plugin_dir = docker_dir / "cli-plugins"
    plugin = plugin_dir / "docker-buildx.exe"
    if (not all(_plain_chain(path, directory=True) for path in (
            config_dir, program_files, docker_dir, plugin_dir))
            or not _plain_chain(plugin, directory=False)
            or _names(config_dir)
            or _names(program_files) != {"Docker"}
            or _names(docker_dir) != {"cli-plugins"}
            or _names(plugin_dir) != {"docker-buildx.exe"}
            or _sha256(plugin) != plugin_sha256):
        raise LayoutDenied("isolated plugin layout mismatch")
    return {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "DOCKER_CONFIG": str(config_dir),
        "ProgramFiles": str(program_files),
    }
