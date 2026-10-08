"""Synthetic Docker inspect records only; no daemon, socket, or receiver."""

import ast
import copy
import inspect
from types import SimpleNamespace

import pytest

from tools.hermes_core import kilo_fake_raw_peer as subject
from tools.hermes_core.kilo_fake_peer_binding import SyntheticAcceptedPeer


def records():
    network_id, receiver_id, gateway_id = "e" * 64, "f" * 64, "a" * 64
    name = "ea4e-fake-attempt"
    scope = SimpleNamespace(network_id=network_id, container_id=receiver_id)
    binding = subject.FakeRawPeerBinding(name, gateway_id)
    network = {
        "Id": network_id, "Name": name, "Driver": "bridge",
        "Internal": True, "EnableIPv6": False,
        "Containers": {
            receiver_id: {"IPv4Address": "172.20.0.2/16"},
            gateway_id: {"IPv4Address": "172.20.0.3/16"},
        },
    }

    def container(identity, ip):
        return {
            "Id": identity, "State": {"Running": True},
            "HostConfig": {"NetworkMode": name, "PublishAllPorts": False,
                           "PortBindings": {}},
            "NetworkSettings": {
                "Networks": {name: {"NetworkID": network_id,
                                   "IPAddress": ip,
                                   "GlobalIPv6Address": ""}},
                "Ports": {"3080/tcp": None},
            },
        }

    return dict(scope=scope, binding=binding,
                context=SyntheticAcceptedPeer("172.20.0.2"), network=network,
                receiver=container(receiver_id, "172.20.0.2"),
                gateway=container(gateway_id, "172.20.0.3"))


def test_raw_fake_peer_match_is_not_attestation():
    assert subject.inspect_fake_raw_peer(**records()) == {
        "decision": "FAKE_RAW_PEER_MATCH_ONLY", "peer_qualified": False,
    }


@pytest.mark.parametrize("change", [
    lambda v: v["network"].update(Internal=False),
    lambda v: v["network"].update(EnableIPv6=True),
    lambda v: v["network"]["Containers"].update({"other": {"IPv4Address": "172.20.0.4/16"}}),
    lambda v: v["receiver"]["State"].update(Running=False),
    lambda v: v["receiver"]["HostConfig"].update(NetworkMode="bridge"),
    lambda v: v["receiver"]["NetworkSettings"]["Networks"].update(other={}),
    lambda v: v["receiver"]["NetworkSettings"]["Networks"][v["binding"].network_name].update(NetworkID=""),
    lambda v: v["receiver"]["NetworkSettings"]["Networks"][v["binding"].network_name].update(IPAddress="172.20.0.4"),
    lambda v: v["gateway"]["NetworkSettings"]["Networks"][v["binding"].network_name].update(GlobalIPv6Address="fd00::2"),
    lambda v: v["receiver"]["HostConfig"].update(PortBindings={"3080/tcp": [{}]}),
    lambda v: v["gateway"]["NetworkSettings"]["Ports"].update({"3080/tcp": [{"HostPort": "3080"}]}),
    lambda v: v.update(context=SyntheticAcceptedPeer("172.20.0.3")),
    lambda v: v.update(context=("172.20.0.2", 4321)),
    lambda v: v.update(scope=SimpleNamespace()),
], ids=["external-network", "ipv6", "extra-member", "stopped",
        "host-mode", "extra-attachment", "missing-endpoint-id",
        "endpoint-ip-drift", "ipv6-endpoint", "port-binding",
        "published-port", "wrong-socket-peer", "untyped-context", "missing-scope"])
def test_raw_fake_peer_denies_drift(change):
    values = copy.deepcopy(records())
    change(values)
    with pytest.raises(subject.FakeRawPeerDenied):
        subject.inspect_fake_raw_peer(**values)


def test_raw_fake_peer_has_no_runtime_imports():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert imports == {"dataclasses", "ipaddress",
                       "tools.hermes_core.docker_peer_candidate",
                       "tools.hermes_core.kilo_fake_peer_binding"}
