"""Environment-gated strict non-live process guard for Hermes qualification."""

from __future__ import annotations

import yaml  # noqa: F401  keep PyYAML importable after app.py mutates sys.path

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path


_ENABLED = os.environ.get("EA4E_STRICT_NONLIVE") == "1"
_HELPER = (
    Path(__file__).resolve().parent / "fixtures" / "durable_auth_process_helper.py"
).resolve()
_PYTHON = Path(sys.executable).resolve()
_AUDIT_PATH = os.environ.get("EA4E_STRICT_PROCESS_AUDIT")
_ORIGINAL_POPEN = subprocess.Popen
_ORIGINAL_RUN = subprocess.run
_ORIGINAL_ASYNC_EXEC = asyncio.create_subprocess_exec
_ORIGINAL_ASYNC_SHELL = asyncio.create_subprocess_shell


def _command_parts(command) -> list[str]:
    if isinstance(command, (str, bytes, os.PathLike)):
        return [os.fsdecode(command)]
    return [os.fsdecode(part) for part in command]


def _is_exact_sqlite_helper(parts: list[str]) -> bool:
    if len(parts) < 3 or parts[1] == "-c":
        return False
    try:
        executable = Path(parts[0]).resolve()
        helper = Path(parts[1]).resolve()
    except (OSError, ValueError):
        return False
    return (
        executable == _PYTHON
        and helper == _HELPER
        and parts[2] in {"claim", "precommit-crash"}
    )


def _receiver_name(parts: list[str]) -> str | None:
    if not parts:
        return None
    name = Path(parts[0]).name.lower()
    for receiver in ("opencode", "kilo", "codex"):
        if receiver in name:
            return receiver
    return None


def _audit(action: str, parts: list[str]) -> None:
    if not _AUDIT_PATH:
        return
    record = {
        "action": action,
        "receiver": _receiver_name(parts),
        "argv": parts,
    }
    with open(_AUDIT_PATH, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def _validate(command) -> list[str]:
    parts = _command_parts(command)
    if _is_exact_sqlite_helper(parts):
        return parts
    _audit("BLOCKED", parts)
    raise AssertionError(f"EA4E33B_FORBIDDEN_PROCESS_ATTEMPT: {parts!r}")


def _guarded_popen(command, *args, **kwargs):
    parts = _validate(command)
    _audit("ALLOWED_SQLITE_HELPER", parts)
    return _ORIGINAL_POPEN(command, *args, **kwargs)


def _guarded_run(command, *args, **kwargs):
    _validate(command)
    return _ORIGINAL_RUN(command, *args, **kwargs)


async def _blocked_async_exec(*args, **kwargs):
    parts = [os.fsdecode(part) for part in args]
    _audit("BLOCKED_ASYNC_EXEC", parts)
    raise AssertionError(f"EA4E33B_FORBIDDEN_ASYNC_PROCESS_ATTEMPT: {parts!r}")


async def _blocked_async_shell(command, *args, **kwargs):
    parts = [os.fsdecode(command)]
    _audit("BLOCKED_ASYNC_SHELL", parts)
    raise AssertionError(f"EA4E33B_FORBIDDEN_ASYNC_SHELL_ATTEMPT: {parts!r}")


if _ENABLED:
    subprocess.Popen = _guarded_popen
    subprocess.run = _guarded_run
    asyncio.create_subprocess_exec = _blocked_async_exec
    asyncio.create_subprocess_shell = _blocked_async_shell


def pytest_sessionfinish(session, exitstatus):
    if _ENABLED:
        subprocess.Popen = _ORIGINAL_POPEN
        subprocess.run = _ORIGINAL_RUN
        asyncio.create_subprocess_exec = _ORIGINAL_ASYNC_EXEC
        asyncio.create_subprocess_shell = _ORIGINAL_ASYNC_SHELL
