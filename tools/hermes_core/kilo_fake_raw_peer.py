"""Pure Docker-shaped peer evidence for the networkless Kilo fake gateway."""

from dataclasses import dataclass
from ipaddress import IPv4Interface

from tools.hermes_core.docker_peer_candidate import (
    PeerCandidateDenied,
    inspect_candidate_peer,
)
from tools.hermes_core.kilo_fake_peer_binding import SyntheticAcceptedPeer


class FakeRawPeerDenied(ValueError):
    pass


@dataclass(frozen=True)
class FakeRawPeerBinding:
    network_name: str
    gateway_id: str


def inspect_fake_raw_peer(scope, binding, context, network, receiver, gateway):
    """Compare supplied records only; no Docker read or socket ownership proof."""
    network_id = getattr(scope, "network_id", None)
    receiver_id = getattr(scope, "container_id", None)
    if (type(binding) is not FakeRawPeerBinding
            or type(context) is not SyntheticAcceptedPeer
            or type(network_id) is not str or not network_id
            or type(receiver_id) is not str or not receiver_id
            or type(binding.network_name) is not str or not binding.network_name
            or type(binding.gateway_id) is not str or not binding.gateway_id
            or not all(type(item) is dict for item in (network, receiver, gateway))):
        raise FakeRawPeerDenied("raw peer input denied")
    if (network.get("Id") != network_id
            or network.get("Name") != binding.network_name
            or network.get("Driver") != "bridge"
            or network.get("Internal") is not True
            or network.get("EnableIPv6") is not False):
        raise FakeRawPeerDenied("network identity denied")
    members = network.get("Containers")
    expected_ids = {receiver_id, binding.gateway_id}
    if type(members) is not dict or set(members) != expected_ids:
        raise FakeRawPeerDenied("network membership denied")
    member_ips = {}
    for identity, member in members.items():
        if type(member) is not dict:
            raise FakeRawPeerDenied("member record denied")
        cidr = member.get("IPv4Address")
        try:
            address = IPv4Interface(cidr)
        except (ValueError, TypeError) as exc:
            raise FakeRawPeerDenied("member address denied") from exc
        if str(address) != cidr:
            raise FakeRawPeerDenied("member address denied")
        member_ips[identity] = str(address.ip)

    normalized = []
    for container, identity in ((receiver, receiver_id),
                                (gateway, binding.gateway_id)):
        state = container.get("State")
        host = container.get("HostConfig")
        settings = container.get("NetworkSettings")
        if (container.get("Id") != identity
                or not all(type(item) is dict for item in (state, host, settings))):
            raise FakeRawPeerDenied("container identity denied")
        attached = settings.get("Networks")
        if (type(attached) is not dict
                or set(attached) != {binding.network_name}
                or type(attached[binding.network_name]) is not dict):
            raise FakeRawPeerDenied("container attachment denied")
        endpoint = attached[binding.network_name]
        ports = settings.get("Ports")
        if (state.get("Running") is not True
                or host.get("NetworkMode") != binding.network_name
                or host.get("PublishAllPorts") is not False
                or host.get("PortBindings") not in (None, {})
                or type(ports) is not dict
                or any(value is not None for value in ports.values())
                or endpoint.get("NetworkID") != network_id
                or endpoint.get("IPAddress") != member_ips[identity]
                or endpoint.get("GlobalIPv6Address") not in (None, "")):
            raise FakeRawPeerDenied("endpoint or host policy denied")
        normalized.append({"id": identity, "running": True,
                           "network_ids": [network_id],
                           "published_ports": []})
    try:
        inspect_candidate_peer(
            network_id=network_id,
            receiver_id=receiver_id,
            gateway_id=binding.gateway_id,
            network={"id": network_id, "driver": "bridge",
                     "internal": True, "members": member_ips},
            receiver=normalized[0], gateway=normalized[1],
            socket_peer_ip=context.peer_ip,
        )
    except PeerCandidateDenied as exc:
        raise FakeRawPeerDenied("socket peer comparison denied") from exc
    return {"decision": "FAKE_RAW_PEER_MATCH_ONLY", "peer_qualified": False}
