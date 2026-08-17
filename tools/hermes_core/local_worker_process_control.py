"""EA-4D.3E-C process control: the ONLY module authorized to spawn the probe.

This module owns the real ``subprocess.Popen`` call. It is deliberately narrow:
it constructs an argv list (never a shell command string), uses ``shell=False``,
and applies THREE independently bounded timeouts that are mechanically enforced:

- ``ack_timeout_seconds``     -> bounded acknowledgement I/O via
                                 ``communicate(input=..., timeout=...)``. A
                                 child that never emits (or commits after the
                                 bound) cannot hang the adapter past this bound.
- ``shutdown_timeout_seconds`` -> bounded terminate/kill of the OWNED child on
                                 ack timeout/error (via ``_terminate``).
- ``lookup_timeout_seconds``  -> bounded SQLite lookup (enforced in the
                                 idempotency registry via busy_timeout); a
                                 locked/unavailable registry normalizes to
                                 UNKNOWN rather than hanging.

PROCESS CREATION IS SYNCHRONOUS (by governance decision for this milestone):
    proc = subprocess.Popen(...)
yields exactly two clean states:
    - a definitive construction exception (FileNotFoundError / PermissionError /
      OSError) -> the process was NOT established -> normalized to FAILED; or
    - a returned process handle -> the process exists -> continue to bounded
      acknowledgement handling.

There is deliberately NO thread-wrapped / daemon spawn timeout around the Popen
constructor. A thread join cannot cancel Popen(); timing out the join while the
constructor is still running would let a process be created AFTER the adapter
returned FAILED, which creates a duplicate-execution race. Synchronous creation
preserves the clean EA-4D.3E boundary: pre-delivery failure vs. process-exists.

Prohibited patterns (per the authorization packet): shell=True, os.system,
requests/httpx/urllib/socket, Playwright, Docker, SSH, Ollama, cmd/bash/powershell
/sh -c, eval, exec. None of those appear here. There is exactly ONE synchronous
subprocess.Popen call site in this module.
"""

import subprocess
import sys


# Local exception type for "the probe process could not be created".
class ProcessSpawnError(RuntimeError):
    """Definitive failure to create the probe process (pre-delivery)."""


def _windows_creation_flags():
    # CREATE_NO_WINDOW avoids spawning a visible console window on Windows for
    # the deterministic probe. No effect on other platforms.
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _terminate(proc, shutdown_timeout_seconds):
    """Terminate/kill ONLY the owned child within the shutdown bound."""
    try:
        proc.terminate()
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.wait(timeout=shutdown_timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(timeout=shutdown_timeout_seconds)
        except Exception:  # noqa: BLE001
            pass


def spawn_probe(
    *,
    executable,
    argv,
    cwd,
    environment,
    request_json,
    ack_timeout_seconds,
    shutdown_timeout_seconds,
    popen_factory=subprocess.Popen,
):
    """Spawn the deterministic probe, deliver one request, bound the ack read.

    Process creation is SYNCHRONOUS: ``popen_factory`` either raises a
    definitive construction exception or returns a concrete owned process
    handle. Only AFTER a handle exists do we apply the bounded acknowledgement
    I/O. On ack timeout the child is terminated within ``shutdown_timeout_seconds``
    and ``("", <partial>)`` is returned; the caller reconciles authoritative
    state via the idempotency registry rather than trusting the ack.

    Returns ``(return_code, stdout_text)``.
    """
    try:
        proc = popen_factory(
            [executable, *argv],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=dict(environment),  # LaunchCommand.environment is a tuple of pairs
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_windows_creation_flags(),
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        # Definitive pre-delivery failure: Popen did not establish a process.
        raise ProcessSpawnError(
            f"probe process could not be created: {exc}")

    try:
        stdout_text, _stderr_text = proc.communicate(
            input=request_json + "\n", timeout=ack_timeout_seconds)
        return proc.returncode, stdout_text.strip()
    except subprocess.TimeoutExpired:
        # Acknowledgement I/O exceeded the bound. Terminate ONLY the owned
        # child within the shutdown window; do not project STARTED.
        _terminate(proc, shutdown_timeout_seconds)
        return proc.returncode, ""
    finally:
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if pipe is not None:
                    pipe.close()
            except Exception:  # noqa: BLE001
                pass


class LocalWorkerProcessControl:
    """Production process-control seam.

    Wraps ``spawn_probe`` and holds the (real) popen factory. Tests may inject a
    factory, but creation remains SYNCHRONOUS — there is no thread-wrapped
    spawn-timeout abstraction.
    """

    def __init__(self, popen_factory=subprocess.Popen) -> None:
        self._popen_factory = popen_factory

    def spawn_probe(self, *, executable, argv, cwd, environment, request_json,
                    ack_timeout_seconds, shutdown_timeout_seconds):
        return spawn_probe(
            executable=executable,
            argv=argv,
            cwd=cwd,
            environment=environment,
            request_json=request_json,
            ack_timeout_seconds=ack_timeout_seconds,
            shutdown_timeout_seconds=shutdown_timeout_seconds,
            popen_factory=self._popen_factory,
        )
