"""R12E-only local process capability for the qualified Codex adapter."""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .codex_adapter import (
    MAX_FINAL_OUTPUT_BYTES,
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    CodexArgv,
    CodexProcessError,
    CodexProcessResult,
)


@dataclass
class _OwnedProcess:
    process: subprocess.Popen
    output_path: Path
    stdout_path: Path
    stderr_path: Path
    stdout_handle: object
    stderr_handle: object
    started_at: float
    collected: bool = False


def _read_bounded(path: Path, limit: int) -> str:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    return data.decode("utf-8", errors="replace")


class CodexLiveProcess:
    """Structured, no-shell process control for one trusted Codex binding.

    Only processes created by this instance can be polled or terminated. Output
    is redirected to adapter-owned files so a verbose child cannot deadlock on
    full stdout/stderr pipes.
    """

    def __init__(
        self,
        *,
        popen: Callable = subprocess.Popen,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._popen = popen
        self._monotonic = monotonic
        self._owned: dict[int, _OwnedProcess] = {}

    def start(self, argv: CodexArgv, stdin_data: str) -> int:
        output_path = Path(argv.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = output_path.with_suffix(".stdout.jsonl")
        stderr_path = output_path.with_suffix(".stderr.txt")
        for path in (output_path, stdout_path, stderr_path):
            if path.exists():
                raise CodexProcessError(f"adapter output already exists: {path}")
        stdout_handle = stdout_path.open("xb")
        stderr_handle = stderr_path.open("xb")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = self._popen(
                argv.to_list(),
                stdin=subprocess.PIPE,
                stdout=stdout_handle,
                stderr=stderr_handle,
                cwd=argv.cwd,
                env=dict(argv.env),
                shell=False,
                creationflags=creationflags,
            )
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            raise
        owned = _OwnedProcess(
            process=process,
            output_path=output_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            stdout_handle=stdout_handle,
            stderr_handle=stderr_handle,
            started_at=self._monotonic(),
        )
        self._owned[process.pid] = owned
        try:
            if process.stdin is None:
                raise CodexProcessError("Codex stdin pipe is unavailable")
            process.stdin.write(stdin_data.encode("utf-8"))
            process.stdin.close()
        except Exception:
            # A child can exit after a definitive start but before consuming
            # stdin. Preserve that started process for authoritative polling.
            if process.poll() is None:
                process.terminate()
            return process.pid
        return process.pid

    def poll(self, pid: int) -> Optional[CodexProcessResult]:
        owned = self._owned.get(pid)
        if owned is None:
            raise CodexProcessError("PID is not owned by this Codex process controller")
        returncode = owned.process.poll()
        if returncode is None:
            return None
        if owned.collected:
            raise CodexProcessError("terminal process result was already collected")
        owned.stdout_handle.close()
        owned.stderr_handle.close()
        owned.collected = True
        final_output = (
            _read_bounded(owned.output_path, MAX_FINAL_OUTPUT_BYTES)
            if owned.output_path.exists() else ""
        )
        return CodexProcessResult(
            pid=pid,
            returncode=returncode,
            stdout=_read_bounded(owned.stdout_path, MAX_STDOUT_BYTES),
            stderr=_read_bounded(owned.stderr_path, MAX_STDERR_BYTES),
            final_output=final_output,
            duration_seconds=max(0.0, self._monotonic() - owned.started_at),
        )

    def terminate(self, pid: int) -> None:
        owned = self._owned.get(pid)
        if owned is None:
            raise CodexProcessError("PID is not owned by this Codex process controller")
        if owned.process.poll() is None:
            owned.process.terminate()

    def kill(self, pid: int) -> None:
        owned = self._owned.get(pid)
        if owned is None:
            raise CodexProcessError("PID is not owned by this Codex process controller")
        if owned.process.poll() is None:
            owned.process.kill()
