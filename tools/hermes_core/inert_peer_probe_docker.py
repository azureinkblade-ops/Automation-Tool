"""Bounded CLI driver for one explicitly approved inert peer probe."""

import json
import subprocess
import sys
import time
import uuid

from tools.hermes_core.inert_peer_probe_coordinator import run_inert_peer_probe
from tools.hermes_core.inert_peer_probe_plan import IMAGE_ID


class DockerProbeDriver:
    def __init__(self):
        self.owned_networks = set()
        self.owned_containers = set()
        self.gateway_id = None
        self.signal_sent = False

    @staticmethod
    def _call(argv, timeout=10):
        if not isinstance(argv, list) or argv[:1] != ["docker"]:
            raise ValueError("non-Docker command denied")
        result = subprocess.run(argv, capture_output=True, text=True,
                                timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError("Docker command failed: " + " ".join(argv[1:3])
                               + " (" + result.stderr.strip()[:200] + ")")
        return result.stdout

    def _inspect(self, kind, identity):
        payload = json.loads(self._call(["docker", kind, "inspect", identity]))
        if type(payload) is not list or len(payload) != 1 or type(payload[0]) is not dict:
            raise ValueError("Docker inspect shape denied")
        return payload[0]

    def inspect_image(self, image_id):
        if image_id != IMAGE_ID:
            raise ValueError("image identity denied")
        return self._inspect("image", image_id)

    def network_names(self):
        return self._call(["docker", "network", "ls", "--format", "{{.Name}}"] ).splitlines()

    def container_names(self):
        return self._call(["docker", "container", "ls", "--all", "--format",
                           "{{.Names}}"] ).splitlines()

    def create_network(self, argv):
        identity = self._call(argv).strip()
        if not identity:
            raise ValueError("network create returned no ID")
        self.owned_networks.add(identity)
        return identity

    def create_container(self, argv):
        if argv[-1] not in ("gateway", "client"):
            raise ValueError("container role denied")
        identity = self._call(argv).strip()
        if not identity:
            raise ValueError("container create returned no ID")
        self.owned_containers.add(identity)
        if argv[-1] == "gateway":
            self.gateway_id = identity
        return identity

    def inspect_network(self, identity):
        if identity not in self.owned_networks:
            raise ValueError("unowned network inspect denied")
        return self._inspect("network", identity)

    def inspect_container(self, identity):
        if identity not in self.owned_containers:
            raise ValueError("unowned container inspect denied")
        return self._inspect("container", identity)

    def start_container(self, identity):
        if identity not in self.owned_containers:
            raise ValueError("unowned container start denied")
        self._call(["docker", "container", "start", identity])

    def wait_accepted_event(self, identity, timeout):
        if identity not in self.owned_containers:
            raise ValueError("unowned container logs denied")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            lines = self._call(["docker", "container", "logs", identity], 3).splitlines()
            if lines:
                if len(lines) != 1:
                    raise ValueError("ambiguous gateway event")
                event = json.loads(lines[0])
                if type(event) is not dict or event.get("event") != "PEER_ACCEPTED":
                    raise ValueError("unexpected gateway event")
                return event
            time.sleep(0.15)
        raise TimeoutError("pending peer event not observed")

    def signal_gateway(self, identity, signal):
        if (identity != self.gateway_id or identity not in self.owned_containers
                or signal != "SIGUSR2" or self.signal_sent):
            raise ValueError("gateway release denied")
        self.signal_sent = True
        self._call(["docker", "kill", "--signal=SIGUSR2", identity])

    def wait_container(self, identity, timeout):
        if identity not in self.owned_containers:
            raise ValueError("unowned container wait denied")
        return int(self._call(["docker", "container", "wait", identity], timeout).strip())

    def logs(self, identity):
        if identity not in self.owned_containers:
            raise ValueError("unowned container logs denied")
        return self._call(["docker", "container", "logs", identity])

    def remove_container(self, identity):
        if identity not in self.owned_containers:
            raise ValueError("unowned container cleanup denied")
        self._call(["docker", "container", "rm", "--force", identity])
        self.owned_containers.remove(identity)

    def remove_network(self, identity):
        if identity not in self.owned_networks:
            raise ValueError("unowned network cleanup denied")
        self._call(["docker", "network", "rm", identity])
        self.owned_networks.remove(identity)


def main(argv):
    if argv != ["--approved-once", IMAGE_ID]:
        raise ValueError("exact one-shot image acknowledgement required")
    run_id = uuid.uuid4().hex
    driver = DockerProbeDriver()
    print(json.dumps({"run_id": run_id, "image_id": IMAGE_ID,
                      "status": "STARTING"}, sort_keys=True), flush=True)
    try:
        result = run_inert_peer_probe(driver, run_id)
    except Exception:
        print(json.dumps({"run_id": run_id, "status": "HOLD",
                          "remaining_network_ids": sorted(driver.owned_networks),
                          "remaining_container_ids": sorted(driver.owned_containers)},
                         sort_keys=True), flush=True)
        raise
    print(json.dumps({"run_id": run_id, **result}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
