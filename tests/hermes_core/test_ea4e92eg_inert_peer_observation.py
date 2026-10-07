"""Synthetic daemon records only; no Docker or socket calls."""

import ast
import copy
import inspect

import pytest

from tools.hermes_core import inert_peer_observation as subject
from tools.hermes_core.inert_peer_probe_plan import build_inert_peer_probe_plan


def records():
    plan = build_inert_peer_probe_plan("a" * 32)
    network_id = "network-id"

    def container(name, container_id, ip):
        return {
            "Id": container_id, "Name": "/" + name,
            "State": {"Running": True},
            "HostConfig": {"PortBindings": {}, "PublishAllPorts": False},
            "Mounts": [],
            "NetworkSettings": {
                "Networks": {plan["network_name"]: {
                    "NetworkID": network_id, "IPAddress": ip,
                }},
                "Ports": {"3080/tcp": None},
            },
        }

    return {
        "plan": plan,
        "network": {
            "Id": network_id, "Name": plan["network_name"],
            "Driver": "bridge", "Internal": True,
            "Containers": {
                "client-id": {"IPv4Address": "172.20.0.2/16"},
                "gateway-id": {"IPv4Address": "172.20.0.3/16"},
            },
        },
        "gateway": container(plan["gateway_name"], "gateway-id", "172.20.0.3"),
        "client": container(plan["client_name"], "client-id", "172.20.0.2"),
        "accepted": {"event": "PEER_ACCEPTED", "peer": "172.20.0.2"},
    }


def test_raw_observation_is_only_a_candidate_match():
    assert subject.inspect_inert_peer_observation(**records()) == {
        "decision": "RAW_OBSERVATION_CANDIDATE_ONLY",
        "peer_qualified": False, "release_authorized": False,
    }


@pytest.mark.parametrize("change", [
    lambda v: v["plan"].update(probe_authorized=True),
    lambda v: v["network"].update(Internal=False),
    lambda v: v["network"].update(Driver="host"),
    lambda v: v["network"]["Containers"].update({"foreign-id": {"IPv4Address": "172.20.0.4/16"}}),
    lambda v: v["network"]["Containers"]["client-id"].update(IPv4Address="172.20.0.4/16"),
    lambda v: v["client"]["State"].update(Running=False),
    lambda v: v["gateway"]["State"].update(Running=False),
    lambda v: v["client"]["NetworkSettings"]["Networks"].update(extra={}),
    lambda v: v["gateway"]["NetworkSettings"]["Networks"][v["plan"]["network_name"]].update(NetworkID=""),
    lambda v: v["client"]["NetworkSettings"]["Networks"][v["plan"]["network_name"]].update(IPAddress="172.20.0.4"),
    lambda v: v["gateway"]["HostConfig"].update(PortBindings={"3080/tcp": [{}]}),
    lambda v: v["client"]["NetworkSettings"]["Ports"].update({"3080/tcp": [{"HostPort": "3080"}]}),
    lambda v: v["client"].update(Mounts=[{"Type": "bind"}]),
    lambda v: v["accepted"].update(peer="172.20.0.3"),
    lambda v: v["accepted"].update(forwarded="172.20.0.2"),
    lambda v: v["accepted"].update(event="MARKER_MATCH"),
], ids=["forged-plan", "external-network", "host-driver", "foreign-member",
        "member-ip-drift", "stopped-client", "stopped-gateway", "multihomed", "running-empty-network-id",
        "endpoint-ip-drift", "port-binding", "published-port", "mount",
        "wrong-socket-peer", "forwarded-header", "wrong-event"])
def test_raw_observation_denies_drift(change):
    values = copy.deepcopy(records())
    change(values)
    with pytest.raises(subject.InertPeerObservationDenied):
        subject.inspect_inert_peer_observation(**values)


def test_adapter_has_no_runtime_capability():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert imports == {
        "ipaddress", "tools.hermes_core.docker_peer_candidate",
        "tools.hermes_core.inert_peer_probe_plan",
    }
