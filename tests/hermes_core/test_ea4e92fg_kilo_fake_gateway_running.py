"""Synthetic running/event snapshots only; no Docker or receiver."""

from copy import deepcopy

import pytest

from tools.hermes_core.kilo_fake_gateway_probe_plan import build_fake_gateway_probe_plan
from tools.hermes_core.kilo_fake_gateway_running import (
    FakeGatewayRunningDenied,
    inspect_fake_gateway_running,
)
from tools.hermes_core.kilo_fake_pending_event import FakePendingEvent


def records():
    plan = build_fake_gateway_probe_plan("a" * 32)
    network_id, gateway_id, client_id = "1" * 64, "2" * 64, "3" * 64
    network = {"Id": network_id, "Name": plan["network_name"],
               "Driver": "bridge", "Internal": True, "EnableIPv6": False,
               "Containers": {
                   client_id: {"IPv4Address": "172.20.0.2/16"},
                   gateway_id: {"IPv4Address": "172.20.0.3/16"},
               }}
    def container(role, identity, ip):
        return {"Id": identity, "Name": "/" + plan[role + "_name"],
                "Image": plan[role + "_index_id"],
                "State": {"Running": True},
                "Config": {"Image": plan[role + "_image"],
                           "Labels": {"hermes.ea4e.run": plan["run_id"]}},
                "HostConfig": {"NetworkMode": plan["network_name"],
                               "PublishAllPorts": False, "PortBindings": {},
                               "ReadonlyRootfs": True, "Privileged": False,
                               "CapDrop": ["ALL"],
                               "SecurityOpt": ["no-new-privileges:true"]},
                "Mounts": [],
                "NetworkSettings": {"Networks": {plan["network_name"]: {
                    "NetworkID": network_id, "IPAddress": ip,
                    "GlobalIPv6Address": ""}},
                    "Ports": {"3080/tcp": None}}}
    event = FakePendingEvent("172.20.0.2",
                             plan["expected_event"]["body_bytes"],
                             plan["expected_event"]["body_sha256"])
    return [plan, event, network,
            container("gateway", gateway_id, "172.20.0.3"),
            container("client", client_id, "172.20.0.2")]


def test_matching_running_records_remain_non_authoritative():
    assert inspect_fake_gateway_running(*records()) == {
        "decision": "FAKE_RUNNING_MATCH_ONLY",
        "peer_qualified": False, "release_authorized": False,
        "production_ready": False,
    }


@pytest.mark.parametrize("mutate", [
    lambda v: v.__setitem__(1, FakePendingEvent("172.20.0.3",
        v[1].body_bytes, v[1].body_sha256)),
    lambda v: v.__setitem__(1, FakePendingEvent("172.20.0.2",
        v[1].body_bytes + 1, v[1].body_sha256)),
    lambda v: v.__setitem__(1, FakePendingEvent("172.20.0.2",
        v[1].body_bytes, "0" * 64)),
    lambda v: v[2].update(Internal=False),
    lambda v: v[2]["Containers"].update({"other": {"IPv4Address": "172.20.0.4/16"}}),
    lambda v: v[3].update(Image="wrong"),
    lambda v: v[3].update(Image=v[0]["gateway_platform_manifest"]),
    lambda v: v[3].update(Mounts=[{}]),
    lambda v: v[4]["State"].update(Running=False),
    lambda v: v[4]["Config"]["Labels"].update({"hermes.ea4e.run": "wrong"}),
    lambda v: v[4]["NetworkSettings"]["Ports"].update({"8181/tcp": [{}]}),
])
def test_event_or_running_drift_denied(mutate):
    values = deepcopy(records())
    mutate(values)
    with pytest.raises(FakeGatewayRunningDenied):
        inspect_fake_gateway_running(*values)
