"""Pure raw-inspect adapter for an in-flight inert peer observation."""

from ipaddress import IPv4Interface

from tools.hermes_core.docker_peer_candidate import (
    PeerCandidateDenied,
    inspect_candidate_peer,
)
from tools.hermes_core.inert_peer_probe_plan import build_inert_peer_probe_plan


class InertPeerObservationDenied(ValueError):
    pass


def inspect_inert_peer_observation(plan: dict, network: dict, gateway: dict,
                                   client: dict, accepted: dict) -> dict:
    """Compare supplied records only; caller must establish fresh timing."""
    if not all(type(item) is dict for item in
               (plan, network, gateway, client, accepted)):
        raise InertPeerObservationDenied("missing observation")
    try:
        canonical = build_inert_peer_probe_plan(plan.get("run_id"))
    except ValueError as exc:
        raise InertPeerObservationDenied("plan denied") from exc
    if plan != canonical:
        raise InertPeerObservationDenied("plan denied")
    if (accepted.get("event") != "PEER_ACCEPTED"
            or set(accepted) != {"event", "peer"}):
        raise InertPeerObservationDenied("accepted event denied")
    network_id = network.get("Id")
    client_id = client.get("Id")
    gateway_id = gateway.get("Id")
    if (network.get("Name") != plan.get("network_name")
            or client.get("Name") != "/" + str(plan.get("client_name"))
            or gateway.get("Name") != "/" + str(plan.get("gateway_name"))
            or any(type(value) is not str or not value for value in
                   (network_id, client_id, gateway_id))):
        raise InertPeerObservationDenied("identity denied")
    members = network.get("Containers")
    if type(members) is not dict or set(members) != {client_id, gateway_id}:
        raise InertPeerObservationDenied("network membership denied")
    member_ips = {}
    for container_id, member in members.items():
        if type(member) is not dict:
            raise InertPeerObservationDenied("member record denied")
        cidr = member.get("IPv4Address")
        try:
            address = IPv4Interface(cidr)
        except (ValueError, TypeError) as exc:
            raise InertPeerObservationDenied("member address denied") from exc
        if str(address) != cidr:
            raise InertPeerObservationDenied("member address denied")
        member_ips[container_id] = str(address.ip)

    normalized = []
    for container, container_id in ((client, client_id), (gateway, gateway_id)):
        state = container.get("State")
        host = container.get("HostConfig")
        settings = container.get("NetworkSettings")
        if not all(type(item) is dict for item in (state, host, settings)):
            raise InertPeerObservationDenied("container record denied")
        attached = settings.get("Networks")
        if (type(attached) is not dict
                or set(attached) != {plan.get("network_name")}
                or type(attached[plan["network_name"]]) is not dict):
            raise InertPeerObservationDenied("container attachment denied")
        endpoint = attached[plan["network_name"]]
        if (endpoint.get("NetworkID") != network_id
                or endpoint.get("IPAddress") != member_ips[container_id]
                or host.get("PortBindings") not in (None, {})
                or host.get("PublishAllPorts") is not False
                or container.get("Mounts") != []):
            raise InertPeerObservationDenied("endpoint or host policy denied")
        ports = settings.get("Ports")
        if type(ports) is not dict or any(value is not None for value in ports.values()):
            raise InertPeerObservationDenied("published port denied")
        normalized.append({"id": container_id,
                           "running": state.get("Running"),
                           "network_ids": [network_id],
                           "published_ports": []})
    try:
        inspect_candidate_peer(
            network_id=network_id, receiver_id=client_id, gateway_id=gateway_id,
            network={"id": network_id, "driver": network.get("Driver"),
                     "internal": network.get("Internal"), "members": member_ips},
            receiver=normalized[0], gateway=normalized[1],
            socket_peer_ip=accepted.get("peer"),
        )
    except PeerCandidateDenied as exc:
        raise InertPeerObservationDenied("peer comparison denied") from exc
    return {"decision": "RAW_OBSERVATION_CANDIDATE_ONLY",
            "peer_qualified": False, "release_authorized": False}
