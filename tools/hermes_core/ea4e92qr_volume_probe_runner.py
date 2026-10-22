"""Unwired, read-only volume probe supervisor candidate; not issuer authority."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import threading

from tools.hermes_core.delegated_task import DelegationIntegrityError


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SID = re.compile(r"S-1-5-21-(?:\d+-){3}\d+\Z")
_CEREMONY = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
_DEADLINE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


@dataclass(frozen=True)
class VolumeProbeOutcome:
    exit_code: int
    stdout: bytes
    stderr: bytes


class BoundedVolumeProbeRunner:
    """One process-local attempt; the operator grant and durable ledger are external."""

    def __init__(self, executable: str, executable_sha256: str,
                 expected_programdata: str, operator_sid: str,
                 ceremony: str, deadline_utc: str, *,
                 popen_factory=subprocess.Popen):
        self.executable = Path(executable)
        self.expected_programdata = expected_programdata
        self.operator_sid = operator_sid
        self.ceremony = ceremony
        self.deadline_utc = deadline_utc
        self.executable_sha256 = executable_sha256
        self.popen_factory = popen_factory
        self._lock = threading.Lock()
        self._attempted = False

    def _screen(self) -> datetime:
        if (not self.executable.is_absolute() or self.executable.is_symlink()
                or not self.executable.is_file()
                or type(self.executable_sha256) is not str
                or not _DIGEST.fullmatch(self.executable_sha256)
                or type(self.expected_programdata) is not str
                or not Path(self.expected_programdata).is_absolute()
                or type(self.operator_sid) is not str
                or not _SID.fullmatch(self.operator_sid)
                or type(self.ceremony) is not str
                or not _CEREMONY.fullmatch(self.ceremony)
                or type(self.deadline_utc) is not str
                or not _DEADLINE.fullmatch(self.deadline_utc)
                or not callable(self.popen_factory)):
            raise DelegationIntegrityError("volume probe binding denied")
        try:
            deadline = datetime.strptime(
                self.deadline_utc, "%Y-%m-%dT%H:%M:%SZ",
            ).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise DelegationIntegrityError("volume probe deadline denied") from exc
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0 or remaining > 120:
            raise DelegationIntegrityError("volume probe deadline denied")
        digest = hashlib.sha256()
        try:
            with self.executable.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise DelegationIntegrityError("volume probe executable unavailable") from exc
        if digest.hexdigest() != self.executable_sha256:
            raise DelegationIntegrityError("volume probe executable changed")
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise DelegationIntegrityError("volume probe deadline denied")
        return deadline

    def __call__(self) -> VolumeProbeOutcome:
        with self._lock:
            if self._attempted:
                raise DelegationIntegrityError("volume probe attempt consumed")
            self._attempted = True
        deadline = self._screen()
        argv = [str(self.executable), "--native-volume",
                self.expected_programdata, self.operator_sid,
                self.ceremony, self.deadline_utc]
        environment = {
            key: os.environ[key] for key in ("SystemRoot", "WINDIR")
            if key in os.environ
        }
        environment["PATH"] = str(self.executable.parent)
        if (deadline - datetime.now(timezone.utc)).total_seconds() <= 0:
            raise DelegationIntegrityError("volume probe deadline denied")
        try:
            proc = self.popen_factory(
                argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=str(self.executable.parent),
                env=environment, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise DelegationIntegrityError("volume probe spawn unavailable") from exc
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        overflow = threading.Event()
        errors = []
        readers = []
        outcome = None

        def read_stream(stream, name):
            try:
                while chunk := stream.read(256):
                    remaining = 256 - len(buffers[name])
                    buffers[name].extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        overflow.set()
                        proc.kill()
                        break
            except Exception as exc:
                errors.append(exc)
                try:
                    proc.kill()
                except OSError:
                    pass

        try:
            if proc.stdout is None or proc.stderr is None:
                raise DelegationIntegrityError("volume probe pipes unavailable")
            for stream, name in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
                reader = threading.Thread(target=read_stream, args=(stream, name),
                                          daemon=True)
                reader.start()
                readers.append(reader)
            remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                raise DelegationIntegrityError("volume probe deadline denied")
            try:
                proc.wait(timeout=min(5.0, remaining))
            except subprocess.TimeoutExpired as exc:
                raise DelegationIntegrityError("volume probe timeout") from exc
            except Exception as exc:
                raise DelegationIntegrityError("volume probe wait uncertain") from exc
            for reader in readers:
                remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
                if remaining <= 0:
                    raise DelegationIntegrityError("volume probe deadline denied")
                reader.join(timeout=min(1.0, remaining))
            if any(reader.is_alive() for reader in readers) or overflow.is_set() or errors:
                raise DelegationIntegrityError("volume probe output uncertain")
            if type(proc.returncode) is not int:
                raise DelegationIntegrityError("volume probe exit uncertain")
            if (deadline - datetime.now(timezone.utc)).total_seconds() <= 0:
                raise DelegationIntegrityError("volume probe deadline denied")
            outcome = VolumeProbeOutcome(proc.returncode, bytes(buffers["stdout"]),
                                         bytes(buffers["stderr"]))
        finally:
            cleanup_error = None
            if outcome is None:
                try:
                    self._kill_and_wait(proc)
                except Exception as exc:
                    cleanup_error = exc
            for reader in readers:
                try:
                    reader.join(timeout=1)
                except Exception as exc:
                    cleanup_error = exc
            if any(reader.is_alive() for reader in readers):
                cleanup_error = DelegationIntegrityError("volume probe readers alive")
            else:
                for stream in (proc.stdout, proc.stderr):
                    if stream is None:
                        continue
                    try:
                        stream.close()
                    except Exception as exc:
                        cleanup_error = exc
            if cleanup_error is not None:
                raise DelegationIntegrityError("volume probe cleanup uncertain") from cleanup_error
        if (deadline - datetime.now(timezone.utc)).total_seconds() <= 0:
            raise DelegationIntegrityError("volume probe deadline denied")
        return outcome

    @staticmethod
    def _kill_and_wait(proc):
        error = None
        try:
            if proc.returncode is None:
                proc.kill()
        except Exception as exc:
            error = exc
        try:
            proc.wait(timeout=1)
        except Exception as exc:
            error = exc
        if error is not None:
            raise DelegationIntegrityError("volume probe cleanup uncertain") from error
