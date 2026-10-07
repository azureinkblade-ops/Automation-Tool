"""Inert coordinator ordering with a fake driver; no Docker calls."""

import copy

import pytest

from tools.hermes_core.inert_peer_probe_coordinator import (
    InertPeerProbeDenied,
    run_inert_peer_probe,
)
from tools.hermes_core.inert_peer_probe_plan import build_inert_peer_probe_plan


class FakeDriver:
    def __init__(self, *, wrong_peer=False, wrong_created=False, bad_marker=False):
        self.plan = build_inert_peer_probe_plan("a" * 32)
        self.calls = []
        self.started = set()
        self.wrong_peer = wrong_peer
        self.wrong_created = wrong_created
        self.bad_marker = bad_marker
        self.image = {
            "Id": self.plan["image_id"], "Os": "linux", "Architecture": "amd64",
            "Config": {"User": "node", "Entrypoint": ["node", "/opt/ea4e-peer/marker.js"],
                       "WorkingDir": "/opt/ea4e-peer", "Env": ["PATH=/bin"],
                       "ExposedPorts": {"3080/tcp": {}}},
        }

    def inspect_image(self, image_id):
        self.calls.append("image")
        assert image_id == self.plan["image_id"]
        return copy.deepcopy(self.image)

    def network_names(self):
        self.calls.append("network-names")
        return []

    def container_names(self):
        self.calls.append("container-names")
        return []

    def create_network(self, argv):
        self.calls.append("create-network")
        assert argv == self.plan["network_create"]
        return "network-id"

    def create_container(self, argv):
        mode = argv[-1]
        self.calls.append("create-" + mode)
        assert argv == self.plan[mode + "_create"]
        return mode + "-id"

    def inspect_network(self, network_id):
        self.calls.append("inspect-network")
        assert network_id == "network-id"
        members = {}
        if "client-id" in self.started:
            members = {
                "client-id": {"IPv4Address": "172.20.0.2/16"},
                "gateway-id": {"IPv4Address": "172.20.0.3/16"},
            }
        return {"Id": network_id, "Name": self.plan["network_name"],
                "Driver": "bridge", "Internal": True,
                "Labels": {"hermes.ea4e.run": self.plan["run_id"]},
                "Containers": members}

    def inspect_container(self, container_id):
        self.calls.append("inspect-" + container_id)
        mode = container_id.removesuffix("-id")
        name = self.plan[mode + "_name"]
        running = container_id in self.started
        ip = "172.20.0.2" if mode == "client" else "172.20.0.3"
        result = {
            "Id": container_id, "Name": "/" + name,
            "Image": self.plan["image_id"],
            "State": {"Status": "running" if running else "created",
                      "Running": running},
            "Config": {"Image": self.plan["image_id"], "User": "node",
                       "Entrypoint": ["node", "/opt/ea4e-peer/marker.js"],
                       "Cmd": [mode], "WorkingDir": "/opt/ea4e-peer",
                       "Env": ["PATH=/bin"], "ExposedPorts": {"3080/tcp": {}},
                       "Labels": {"hermes.ea4e.run": self.plan["run_id"]}},
            "HostConfig": {"NetworkMode": self.plan["network_name"],
                           "ReadonlyRootfs": True, "Privileged": False,
                           "CapDrop": ["ALL"],
                           "SecurityOpt": ["no-new-privileges:true"],
                           "PidsLimit": 32, "Memory": 268435456,
                           "NanoCpus": 250000000, "PublishAllPorts": False,
                           "PortBindings": {},
                           "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
                           "AutoRemove": False, "Binds": None,
                           "CapAdd": None, "Devices": None},
            "Mounts": [],
            "NetworkSettings": {"Networks": {self.plan["network_name"]: {
                "NetworkID": "network-id", "IPAddress": ip if running else "",
                "Aliases": ["ea4e-peer-gateway"] if mode == "gateway" else [],
            }}, "Ports": {"3080/tcp": None}},
        }
        if self.wrong_created and not running and mode == "client":
            result["HostConfig"]["Privileged"] = True
        return result

    def start_container(self, container_id):
        self.calls.append("start-" + container_id)
        self.started.add(container_id)

    def wait_accepted_event(self, gateway_id, timeout):
        self.calls.append("accepted")
        assert gateway_id == "gateway-id" and timeout == 10
        return {"event": "PEER_ACCEPTED",
                "peer": "172.20.0.3" if self.wrong_peer else "172.20.0.2"}

    def signal_gateway(self, gateway_id, signal):
        self.calls.append("signal")
        assert gateway_id == "gateway-id" and signal == "SIGUSR2"

    def wait_container(self, container_id, timeout):
        self.calls.append("wait-" + container_id)
        return 0

    def logs(self, container_id):
        self.calls.append("logs")
        return "BAD\n" if self.bad_marker else "MARKER_MATCH\n"

    def remove_container(self, container_id):
        self.calls.append("remove-" + container_id)

    def remove_network(self, network_id):
        self.calls.append("remove-network")


def test_success_signals_only_after_running_observation_and_cleans_exact_ids():
    driver = FakeDriver()
    result = run_inert_peer_probe(driver, "a" * 32)
    assert result["decision"] == "INERT_PEER_OBSERVED_ONLY"
    assert result["peer_qualified"] is False
    assert result["production_ready"] is False
    assert driver.calls.index("signal") > driver.calls.index("accepted")
    assert driver.calls[-3:] == ["remove-client-id", "remove-gateway-id", "remove-network"]


@pytest.mark.parametrize("kwargs,expected_last", [
    ({"wrong_created": True}, "remove-network"),
    ({"wrong_peer": True}, "remove-network"),
    ({"bad_marker": True}, "remove-network"),
])
def test_failure_never_skips_exact_cleanup(kwargs, expected_last):
    driver = FakeDriver(**kwargs)
    with pytest.raises((ValueError, InertPeerProbeDenied)):
        run_inert_peer_probe(driver, "a" * 32)
    assert driver.calls[-1] == expected_last
    if kwargs.get("wrong_created") or kwargs.get("wrong_peer"):
        assert "signal" not in driver.calls


def test_preflight_collision_creates_nothing():
    driver = FakeDriver()
    driver.network_names = lambda: [driver.plan["network_name"]]
    with pytest.raises(ValueError):
        run_inert_peer_probe(driver, "a" * 32)
    assert not any(call.startswith("create-") for call in driver.calls)
