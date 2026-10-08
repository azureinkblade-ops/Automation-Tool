"""Synthetic peer binding for the networkless Kilo fake gateway only."""

from dataclasses import dataclass

from tools.hermes_core.docker_peer_candidate import (
    PeerCandidateDenied,
    inspect_candidate_peer,
)


@dataclass(frozen=True)
class SyntheticAcceptedPeer:
    peer_ip: str


@dataclass(frozen=True)
class SyntheticDockerSnapshot:
    network: dict
    receiver: dict
    gateway: dict


def make_fake_peer_verifier(*, gateway_id, read_snapshot):
    """Return a fail-closed injected verifier; this does not read Docker."""
    if type(gateway_id) is not str or not gateway_id or not callable(read_snapshot):
        raise ValueError("fake peer binding configuration denied")

    def verify(scope, context):
        if type(context) is not SyntheticAcceptedPeer:
            return False
        snapshot = read_snapshot()
        if type(snapshot) is not SyntheticDockerSnapshot:
            return False
        try:
            inspect_candidate_peer(
                network_id=scope.network_id,
                receiver_id=scope.container_id,
                gateway_id=gateway_id,
                network=snapshot.network,
                receiver=snapshot.receiver,
                gateway=snapshot.gateway,
                socket_peer_ip=context.peer_ip,
            )
        except PeerCandidateDenied:
            return False
        return True

    return verify
