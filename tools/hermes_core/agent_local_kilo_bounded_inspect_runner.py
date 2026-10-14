"""Opt-in, bounded process runner for the local Kilo Docker inspect client."""

import hashlib
import os
from pathlib import Path
import re
import subprocess
import threading

from tools.hermes_core.delegated_task import DelegationIntegrityError


_ID = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
_LIMIT = 1024 * 1024


class BoundedDockerInspectRunner:
    """Allow only pinned inspect argv; no create/start/signal capability."""

    def __init__(self, executable: str, executable_sha256: str,
                 empty_config_dir: str, *, popen_factory=subprocess.Popen):
        self.executable = Path(executable)
        self.config_dir = Path(empty_config_dir)
        if (not self.executable.is_absolute() or self.executable.is_symlink()
                or not self.executable.is_file()
                or type(executable_sha256) is not str
                or not _ID.fullmatch(executable_sha256)
                or not self.config_dir.is_absolute()
                or not callable(popen_factory)):
            raise DelegationIntegrityError("Docker inspect runner binding denied")
        self.executable_sha256 = executable_sha256
        self.popen_factory = popen_factory

    def _verify(self, argv, timeout_seconds, max_output_bytes):
        if (type(argv) not in (tuple, list) or type(timeout_seconds) is not int
                or timeout_seconds != 5 or type(max_output_bytes) is not int
                or max_output_bytes != _LIMIT or any(type(arg) is not str for arg in argv)
                or tuple(argv[:3]) != (str(self.executable), "--host", _HOST)):
            raise DelegationIntegrityError("Docker inspect argv denied")
        command = tuple(argv[3:])
        if (len(command) == 3 and command[:2] in (("container", "inspect"),
                                                  ("network", "inspect"))
                and _ID.fullmatch(command[2])):
            pass
        elif (len(command) == 5 and command[:4] ==
              ("image", "inspect", "--platform", "linux/amd64")
              and _IMAGE.fullmatch(command[4])):
            pass
        else:
            raise DelegationIntegrityError("Docker inspect command denied")
        if (self.config_dir.is_symlink() or not self.config_dir.is_dir()
                or any(self.config_dir.iterdir())):
            raise DelegationIntegrityError("Docker inspect config denied")
        if self.executable.is_symlink() or not self.executable.is_file():
            raise DelegationIntegrityError("Docker inspect executable unavailable")
        digest = hashlib.sha256()
        try:
            with self.executable.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise DelegationIntegrityError("Docker inspect executable unavailable") from exc
        if digest.hexdigest() != self.executable_sha256:
            raise DelegationIntegrityError("Docker inspect executable changed")

    def __call__(self, argv, *, timeout_seconds, max_output_bytes):
        self._verify(argv, timeout_seconds, max_output_bytes)
        environment = {
            key: os.environ[key] for key in ("SystemRoot", "WINDIR")
            if key in os.environ
        }
        environment.update({
            "PATH": str(self.executable.parent),
            "DOCKER_CONFIG": str(self.config_dir),
        })
        try:
            proc = self.popen_factory(
                list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=str(self.config_dir),
                env=environment, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise DelegationIntegrityError("Docker inspect process unavailable") from exc
        if proc.stdout is None or proc.stderr is None:
            proc.kill()
            proc.wait(timeout=1)
            raise DelegationIntegrityError("Docker inspect pipes unavailable")

        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        overflow = threading.Event()
        errors = []

        def read_stream(stream, name, limit):
            try:
                while chunk := stream.read(65536):
                    remaining = limit - len(buffers[name])
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

        readers = [
            threading.Thread(target=read_stream,
                             args=(proc.stdout, "stdout", _LIMIT), daemon=True),
            threading.Thread(target=read_stream,
                             args=(proc.stderr, "stderr", 4096), daemon=True),
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            proc.wait(timeout=1)
        except Exception as exc:
            try:
                proc.kill()
                proc.wait(timeout=1)
            except Exception:
                pass
            raise DelegationIntegrityError("Docker inspect wait failed") from exc
        for reader in readers:
            reader.join(timeout=1)
        if not any(reader.is_alive() for reader in readers):
            proc.stdout.close()
            proc.stderr.close()
        if (timed_out or overflow.is_set() or errors
                or any(reader.is_alive() for reader in readers)
                or proc.returncode != 0 or buffers["stderr"]):
            raise DelegationIntegrityError("Docker inspect execution denied")
        return bytes(buffers["stdout"])
