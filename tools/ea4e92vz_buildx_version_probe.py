"""Value-only, opt-in standalone Buildx version probe. No daemon operation."""

import hashlib
import os
from pathlib import Path
import re
import subprocess
import threading


class ProbeDenied(Exception):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_version(binary: Path, expected_sha256: str) -> bool:
    """Return only success/failure; never release plugin stdout or stderr."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ProbeDenied("invalid Buildx pin")
    try:
        resolved = binary.resolve(strict=True)
        if not resolved.is_file() or resolved.name.lower() != "docker-buildx.exe":
            raise ProbeDenied("invalid Buildx executable")
        if _sha256(resolved) != expected_sha256:
            raise ProbeDenied("Buildx identity mismatch")
    except OSError:
        raise ProbeDenied("Buildx executable unavailable") from None

    try:
        process = subprocess.Popen(
            (str(resolved), "version"),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")},
        )
    except OSError:
        raise ProbeDenied("Buildx process unavailable") from None
    exceeded = threading.Event()
    captured = bytearray()
    lock = threading.Lock()

    def drain(stream):
        try:
            while chunk := stream.read(4096):
                with lock:
                    remaining = 4096 - len(captured)
                    captured.extend(chunk[:max(0, remaining)])
                    overflow = len(chunk) > remaining
                if overflow:
                    exceeded.set()
                    try:
                        process.kill()
                    except OSError:
                        pass
                    return
        except OSError:
            exceeded.set()
            try:
                process.kill()
            except OSError:
                pass

    readers = [threading.Thread(target=drain, args=(stream,), daemon=True)
               for stream in (process.stdout, process.stderr)]
    for reader in readers:
        reader.start()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=3)
        except OSError:
            pass
        raise ProbeDenied("Buildx deadline exceeded") from None
    finally:
        if process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=3)
            except OSError:
                pass
        for reader in readers:
            reader.join(timeout=2)
    if exceeded.is_set() or any(reader.is_alive() for reader in readers):
        raise ProbeDenied("Buildx output bound failed")
    return process.returncode == 0
