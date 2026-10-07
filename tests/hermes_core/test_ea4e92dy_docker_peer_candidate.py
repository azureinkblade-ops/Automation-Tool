"""Synthetic network snapshots only; never query Docker or open sockets."""

import ast
import copy
import inspect

import pytest

from tools.hermes_core import docker_peer_candidate as subject


def fixture():
    return {
        "network_id": "net-1",
        "receiver_id": "receiver-1",
        "gateway_id": "gateway-1",
        "network": {
            "id": "net-1", "driver": "bridge", "internal": True,
            "members": {"receiver-1": "172.20.0.2", "gateway-1": "172.20.0.3"},
        },
        "receiver": {
            "id": "receiver-1", "running": True,
            "network_ids": ["net-1"], "published_ports": [],
        },
        "gateway": {
            "id": "gateway-1", "running": True,
            "network_ids": ["net-1"], "published_ports": [],
        },
        "socket_peer_ip": "172.20.0.2",
    }


def test_exact_fake_snapshot_is_only_a_candidate():
    assert subject.inspect_candidate_peer(**fixture()) == {
        "decision": "CANDIDATE_MATCH_ONLY", "peer_qualified": False,
    }


@pytest.mark.parametrize("change", [
    lambda v: v.update(socket_peer_ip="172.20.0.1"),
    lambda v: v.update(socket_peer_ip="172.20.0.3"),
    lambda v: v.update(socket_peer_ip="::ffff:172.20.0.2"),
    lambda v: v["network"].update(id="net-stale"),
    lambda v: v["network"].update(driver="host"),
    lambda v: v["network"].update(internal=False),
    lambda v: v["network"]["members"].update({"extra": "172.20.0.4"}),
    lambda v: v["network"]["members"].pop("receiver-1"),
    lambda v: v["network"]["members"].update({"receiver-1": "172.20.0.3"}),
    lambda v: v["receiver"].update(running=False),
    lambda v: v["receiver"].update(network_ids=["net-1", "other"]),
    lambda v: v["receiver"].update(published_ports=["8080"]),
    lambda v: v["gateway"].update(network_ids=[]),
    lambda v: v["gateway"].update(published_ports=["8080"]),
    lambda v: v["gateway"].update(id="substitute"),
], ids=[
    "host-origin", "gateway-origin", "mapped-ipv6", "stale-network",
    "host-driver", "external-network", "extra-member", "missing-member",
    "duplicate-address", "stopped-receiver", "multi-homed-receiver",
    "receiver-published", "detached-gateway", "gateway-published",
    "substitute-gateway",
])
def test_mismatches_fail_closed(change):
    values = copy.deepcopy(fixture())
    change(values)
    with pytest.raises(subject.PeerCandidateDenied):
        subject.inspect_candidate_peer(**values)


def test_no_docker_socket_or_runtime_capability():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert imports == {"ipaddress"}
