"""Pure in-flight fake gateway comparison; no release or peer authority."""

from types import SimpleNamespace

from tools.hermes_core.kilo_fake_gateway_probe_plan import build_fake_gateway_probe_plan
from tools.hermes_core.kilo_fake_pending_event import FakePendingEvent
from tools.hermes_core.kilo_fake_peer_binding import SyntheticAcceptedPeer
from tools.hermes_core.kilo_fake_raw_peer import (
    FakeRawPeerBinding,
    FakeRawPeerDenied,
    inspect_fake_raw_peer,
)


class FakeGatewayRunningDenied(ValueError):
    pass


def inspect_fake_gateway_running(plan, event, network, gateway, client):
    """Match supplied event and running records, but do not authorize release."""
    if (type(plan) is not dict or type(event) is not FakePendingEvent
            or not all(type(item) is dict for item in (network, gateway, client))):
        raise FakeGatewayRunningDenied("running input denied")
    try:
        canonical = build_fake_gateway_probe_plan(plan.get("run_id"))
    except ValueError as exc:
        raise FakeGatewayRunningDenied("running plan denied") from exc
    if (plan != canonical
            or event.body_bytes != plan["expected_event"]["body_bytes"]
            or event.body_sha256 != plan["expected_event"]["body_sha256"]):
        raise FakeGatewayRunningDenied("request event denied")
    network_id = network.get("Id")
    gateway_id = gateway.get("Id")
    client_id = client.get("Id")
    if not all(type(identity) is str and identity for identity in
               (network_id, gateway_id, client_id)):
        raise FakeGatewayRunningDenied("running identity denied")
    label = plan["run_id"]
    for role, container in (("gateway", gateway), ("client", client)):
        config = container.get("Config")
        host = container.get("HostConfig")
        if (container.get("Name") != "/" + plan[role + "_name"]
                or container.get("Image") != plan[role + "_index_id"]
                or type(config) is not dict or type(host) is not dict
                or config.get("Image") != plan[role + "_image"]
                or type(config.get("Labels")) is not dict
                or config["Labels"].get("hermes.ea4e.run") != label
                or host.get("ReadonlyRootfs") is not True
                or host.get("Privileged") is not False
                or host.get("CapDrop") != ["ALL"]
                or host.get("SecurityOpt") != ["no-new-privileges:true"]
                or container.get("Mounts") != []):
            raise FakeGatewayRunningDenied(role + " runtime policy denied")
    try:
        inspect_fake_raw_peer(
            SimpleNamespace(network_id=network_id, container_id=client_id),
            FakeRawPeerBinding(plan["network_name"], gateway_id),
            SyntheticAcceptedPeer(event.peer_ip), network, client, gateway)
    except FakeRawPeerDenied as exc:
        raise FakeGatewayRunningDenied("running peer candidate denied") from exc
    return {"decision": "FAKE_RUNNING_MATCH_ONLY",
            "peer_qualified": False, "release_authorized": False,
            "production_ready": False}
