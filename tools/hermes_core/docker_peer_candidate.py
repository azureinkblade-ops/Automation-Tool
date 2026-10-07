"""Pure candidate for 92DX peer comparison; not Docker attestation."""

from ipaddress import IPv4Address


class PeerCandidateDenied(ValueError):
    pass


def _address(value):
    if type(value) is not str:
        raise PeerCandidateDenied("invalid peer address")
    try:
        address = IPv4Address(value)
    except ValueError as exc:
        raise PeerCandidateDenied("invalid peer address") from exc
    if str(address) != value or address.is_unspecified or address.is_multicast:
        raise PeerCandidateDenied("invalid peer address")
    return address


def inspect_candidate_peer(*, network_id, receiver_id, gateway_id,
                           network, receiver, gateway, socket_peer_ip):
    """Compare normalized fake observations; never grant runtime authority."""
    if not all(type(value) is str and value for value in
               (network_id, receiver_id, gateway_id)):
        raise PeerCandidateDenied("missing expected identity")
    if receiver_id == gateway_id:
        raise PeerCandidateDenied("ambiguous container identity")
    if not all(type(value) is dict for value in
               (network, receiver, gateway)):
        raise PeerCandidateDenied("missing observation")
    members = network.get("members")
    if (network.get("id") != network_id
            or network.get("driver") != "bridge"
            or network.get("internal") is not True
            or type(members) is not dict
            or set(members) != {receiver_id, gateway_id}):
        raise PeerCandidateDenied("network identity or membership denied")
    for observed, expected_id in ((receiver, receiver_id),
                                  (gateway, gateway_id)):
        if (observed.get("id") != expected_id
                or observed.get("running") is not True
                or observed.get("network_ids") != [network_id]
                or observed.get("published_ports") != []):
            raise PeerCandidateDenied("container state denied")
    receiver_ip = _address(members[receiver_id])
    gateway_ip = _address(members[gateway_id])
    if receiver_ip == gateway_ip or _address(socket_peer_ip) != receiver_ip:
        raise PeerCandidateDenied("socket peer denied")
    return {"decision": "CANDIDATE_MATCH_ONLY", "peer_qualified": False}
