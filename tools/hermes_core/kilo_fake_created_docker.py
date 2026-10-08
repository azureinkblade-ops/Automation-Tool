"""Pinned-CLI driver for one never-started fake-gateway diagnostic."""

import hashlib
import json
from pathlib import Path
import re
import subprocess

from tools.hermes_core.kilo_fake_gateway_probe_plan import build_fake_gateway_probe_plan


class FakeCreatedDockerDenied(RuntimeError):
    pass


class FakeCreatedDockerDriver:
    def __init__(self, *, run_id, docker_executable, docker_sha256,
                 run_command=None):
        self.plan = build_fake_gateway_probe_plan(run_id)
        path = Path(docker_executable)
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or type(docker_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", docker_sha256) is None
                or run_command is not None and not callable(run_command)):
            raise FakeCreatedDockerDenied("Docker executable pin denied")
        self.executable = path
        self.digest = docker_sha256
        self.run_command = run_command or self._subprocess_run

    @staticmethod
    def _subprocess_run(argv):
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=10, check=False)

    def _call(self, args, *, allow_absent=False, reject_stderr=False):
        digest = hashlib.sha256()
        try:
            with self.executable.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != self.digest:
                raise FakeCreatedDockerDenied("Docker executable changed")
            result = self.run_command([str(self.executable), *args])
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FakeCreatedDockerDenied("Docker command unavailable") from exc
        if (type(result.returncode) is not int
                or type(result.stdout) is not str or type(result.stderr) is not str
                or len(result.stdout) > 262144 or len(result.stderr) > 4096):
            raise FakeCreatedDockerDenied("Docker result denied")
        if result.returncode:
            if allow_absent and ("No such" in result.stderr
                                 or "not found" in result.stderr):
                return None
            raise FakeCreatedDockerDenied("Docker command failed")
        if reject_stderr and result.stderr:
            raise FakeCreatedDockerDenied("Docker stderr denied")
        return result.stdout

    def _inspect(self, kind, identity, *, allow_absent=False):
        raw = self._call([kind, "inspect", identity], allow_absent=allow_absent)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise FakeCreatedDockerDenied("Docker inspect JSON denied") from exc
        if (type(payload) is not list or len(payload) != 1
                or type(payload[0]) is not dict):
            raise FakeCreatedDockerDenied("Docker inspect shape denied")
        return payload[0]

    def inspect_image(self, image):
        if image not in (self.plan["gateway_image"], self.plan["client_image"]):
            raise FakeCreatedDockerDenied("image reference denied")
        raw = self._call(["image", "inspect", "--platform", "linux/amd64", image])
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise FakeCreatedDockerDenied("image JSON denied") from exc
        if type(payload) is not list or len(payload) != 1 or type(payload[0]) is not dict:
            raise FakeCreatedDockerDenied("image inspect shape denied")
        return payload[0]

    def network_names(self):
        return self._call(["network", "ls", "--format", "{{.Name}}"]).splitlines()

    def container_names(self):
        return self._call(["container", "ls", "--all", "--format",
                           "{{.Names}}"]).splitlines()

    def create_network(self, argv):
        if argv != self.plan["network_create"]:
            raise FakeCreatedDockerDenied("network create argv denied")
        return self._call(argv[1:]).strip()

    def create_container(self, argv):
        if argv not in (self.plan["gateway_create"], self.plan["client_create"]):
            raise FakeCreatedDockerDenied("container create argv denied")
        return self._call(argv[1:]).strip()

    def inspect_network(self, identity):
        return self._inspect("network", identity)

    def inspect_container(self, identity):
        return self._inspect("container", identity)

    def cleanup_owned(self, plan, network_id, gateway_id, client_id):
        if plan != self.plan:
            raise FakeCreatedDockerDenied("cleanup plan denied")
        label = plan["run_id"]
        errors = []
        for role, expected_id in (("client", client_id), ("gateway", gateway_id)):
            try:
                record = self._inspect("container", plan[role + "_name"],
                                       allow_absent=True)
                if record is None:
                    continue
                identity = record.get("Id")
                config = record.get("Config")
                state = record.get("State")
                if (type(identity) is not str
                        or re.fullmatch(r"[0-9a-f]{64}", identity) is None
                        or expected_id is not None and identity != expected_id
                        or record.get("Name") != "/" + plan[role + "_name"]
                        or type(config) is not dict
                        or config.get("Labels", {}).get("hermes.ea4e.run") != label
                        or config.get("Image") != plan[role + "_image"]
                        or type(state) is not dict or state.get("Running") is not False):
                    raise FakeCreatedDockerDenied("container ownership denied")
                self._call(["container", "rm", "--force", identity])
            except Exception as exc:
                errors.append(exc)
        try:
            record = self._inspect("network", plan["network_name"],
                                   allow_absent=True)
            if record is not None:
                identity = record.get("Id")
                if (type(identity) is not str
                        or re.fullmatch(r"[0-9a-f]{64}", identity) is None
                        or network_id is not None and identity != network_id
                        or record.get("Name") != plan["network_name"]
                        or record.get("Labels", {}).get("hermes.ea4e.run") != label
                        or record.get("Containers") not in (None, {})):
                    raise FakeCreatedDockerDenied("network ownership denied")
                self._call(["network", "rm", identity])
        except Exception as exc:
            errors.append(exc)
        remaining_containers = self._call([
            "container", "ls", "--all", "--filter",
            f"label=hermes.ea4e.run={label}", "--format", "{{.ID}}",
        ]).splitlines()
        remaining_networks = self._call([
            "network", "ls", "--filter", f"label=hermes.ea4e.run={label}",
            "--format", "{{.ID}}",
        ]).splitlines()
        if errors:
            raise FakeCreatedDockerDenied("owned cleanup incomplete") from errors[0]
        return {"remaining_network_ids": remaining_networks,
                "remaining_container_ids": remaining_containers}
