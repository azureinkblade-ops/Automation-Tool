"""Read only prebound Docker inspect records for a future Kilo peer check."""

import hashlib
import json
from pathlib import Path
import re
import subprocess

from tools.hermes_core.kilo_fake_raw_peer import FakeRawPeerSnapshot


class ScopedDockerReadDenied(ValueError):
    pass


class ScopedDockerSnapshotReader:
    def __init__(self, *, network_id, receiver_id, gateway_id,
                 docker_executable, docker_sha256, run_command=None):
        identities = (network_id, receiver_id, gateway_id)
        if (any(type(value) is not str
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in identities)
                or len(set(identities)) != 3):
            raise ScopedDockerReadDenied("inspect identities denied")
        if run_command is not None and not callable(run_command):
            raise ScopedDockerReadDenied("inspect runner denied")
        if (type(docker_executable) is not str
                or not Path(docker_executable).is_absolute()
                or type(docker_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", docker_sha256) is None):
            raise ScopedDockerReadDenied("Docker executable pin denied")
        self.network_id = network_id
        self.receiver_id = receiver_id
        self.gateway_id = gateway_id
        self.docker_executable = Path(docker_executable)
        self.docker_sha256 = docker_sha256
        self.run_command = run_command or self._docker_inspect

    def _verify_executable(self):
        path = self.docker_executable
        if path.is_symlink() or not path.is_file():
            raise ScopedDockerReadDenied("Docker executable unavailable")
        digest = hashlib.sha256()
        try:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise ScopedDockerReadDenied("Docker executable unavailable") from exc
        if digest.hexdigest() != self.docker_sha256:
            raise ScopedDockerReadDenied("Docker executable hash denied")

    @staticmethod
    def _docker_inspect(argv):
        try:
            result = subprocess.run(argv, capture_output=True, text=True,
                                    timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ScopedDockerReadDenied("Docker inspect unavailable") from exc
        if result.returncode != 0:
            raise ScopedDockerReadDenied("Docker inspect failed")
        return result.stdout

    def _read_one(self, kind, identity):
        raw = self.run_command([str(self.docker_executable), kind, "inspect", identity])
        if type(raw) is not str or len(raw) > 262144:
            raise ScopedDockerReadDenied("inspect output denied")
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ScopedDockerReadDenied("inspect JSON denied") from exc
        if (type(payload) is not list or len(payload) != 1
                or type(payload[0]) is not dict
                or payload[0].get("Id") != identity):
            raise ScopedDockerReadDenied("inspect identity denied")
        return payload[0]

    def read(self):
        self._verify_executable()
        return FakeRawPeerSnapshot(
            network=self._read_one("network", self.network_id),
            receiver=self._read_one("container", self.receiver_id),
            gateway=self._read_one("container", self.gateway_id),
        )
