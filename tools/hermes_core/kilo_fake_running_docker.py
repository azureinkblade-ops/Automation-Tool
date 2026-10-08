"""Pinned Docker driver for a separately authorized inert running probe."""

import re
import time

from tools.hermes_core.kilo_fake_created_docker import (
    FakeCreatedDockerDenied,
    FakeCreatedDockerDriver,
)
from tools.hermes_core.kilo_fake_pending_event import parse_fake_pending_event


class FakeRunningDockerDriver(FakeCreatedDockerDriver):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.created = {}

    def create_container(self, argv):
        identity = super().create_container(argv)
        role = "gateway" if argv == self.plan["gateway_create"] else "client"
        self.created[role] = identity
        return identity

    def start_container(self, identity):
        if identity not in self.created.values():
            raise FakeCreatedDockerDenied("unowned start denied")
        role = next(role for role, owned in self.created.items()
                    if owned == identity)
        record = self.inspect_container(identity)
        config = record.get("Config")
        state = record.get("State")
        if (record.get("Id") != identity
                or record.get("Name") != "/" + self.plan[role + "_name"]
                or type(config) is not dict
                or config.get("Image") != self.plan[role + "_image"]
                or config.get("Labels", {}).get("hermes.ea4e.run")
                != self.plan["run_id"]
                or type(state) is not dict
                or state.get("Status") != "created"
                or state.get("Running") is not False):
            raise FakeCreatedDockerDenied("start identity denied")
        if self._call(["container", "start", identity]).strip() != identity:
            raise FakeCreatedDockerDenied("start result denied")

    def pending_line(self, identity, timeout):
        if (identity != self.created.get("gateway") or timeout != 10):
            raise FakeCreatedDockerDenied("pending reader scope denied")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self._call(["container", "logs", "--tail", "2", identity],
                             reject_stderr=True)
            if raw:
                if len(raw) > 512:
                    raise FakeCreatedDockerDenied("pending log length denied")
                line = raw.encode("ascii", errors="strict")
                parse_fake_pending_event(line)
                return line
            time.sleep(0.15)
        raise FakeCreatedDockerDenied("pending event timeout")

    def cleanup_running_owned(self, plan, network_id, gateway_id, client_id):
        if plan != self.plan:
            raise FakeCreatedDockerDenied("cleanup plan denied")
        errors = []
        for role, expected in (("client", client_id), ("gateway", gateway_id)):
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
                        or expected is not None and identity != expected
                        or record.get("Name") != "/" + plan[role + "_name"]
                        or type(config) is not dict
                        or config.get("Image") != plan[role + "_image"]
                        or config.get("Labels", {}).get("hermes.ea4e.run")
                        != plan["run_id"]
                        or type(state) is not dict
                        or expected is None and state.get("Running") is not False):
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
                        or record.get("Labels", {}).get("hermes.ea4e.run")
                        != plan["run_id"]
                        or record.get("Containers") not in (None, {})):
                    raise FakeCreatedDockerDenied("network ownership denied")
                self._call(["network", "rm", identity])
        except Exception as exc:
            errors.append(exc)
        remaining = {
            "remaining_container_ids": self._call([
                "container", "ls", "--all", "--filter",
                f"label=hermes.ea4e.run={plan['run_id']}",
                "--format", "{{.ID}}",
            ]).splitlines(),
            "remaining_network_ids": self._call([
                "network", "ls", "--filter",
                f"label=hermes.ea4e.run={plan['run_id']}",
                "--format", "{{.ID}}",
            ]).splitlines(),
        }
        if errors:
            raise FakeCreatedDockerDenied("owned cleanup incomplete") from errors[0]
        return remaining
