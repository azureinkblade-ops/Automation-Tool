"""Compare a reported Kilo ping event with recorded and supplied peer identity."""

from types import SimpleNamespace

from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_local_kilo_fake_launch_candidate import (
    build_agent_local_kilo_fake_launch_candidate,
)
from tools.hermes_core.agent_local_kilo_fake_ping_body import (
    build_agent_local_kilo_fake_ping_body,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.kilo_fake_peer_binding import SyntheticAcceptedPeer
from tools.hermes_core.kilo_fake_raw_peer import (
    FakeRawPeerBinding,
    FakeRawPeerDenied,
    inspect_fake_raw_peer,
)
from tools.hermes_core.kilo_ping_pending_event import (
    PingPendingEventDenied,
    parse_ping_pending_event,
)


def compare_reported_kilo_ping_pending(
    records: SQLiteAgentLocalKiloContainerRecordStore,
    attempt_id: str,
    container_id: str,
    v1_plan: dict,
    event_line: bytes,
    *,
    gateway_id: str,
    network: dict,
    receiver: dict,
    gateway: dict,
) -> dict:
    """Match supplied records only; never inspect Docker or allow release."""
    if type(records) is not SQLiteAgentLocalKiloContainerRecordStore:
        raise DelegationIntegrityError("Kilo pending comparison store denied")
    report = records.get(attempt_id)
    if report is None or report.container_id != container_id:
        raise DelegationIntegrityError("Kilo pending container identity denied")
    intent = records.intents.verify_plan(attempt_id, v1_plan)
    candidate = build_agent_local_kilo_fake_launch_candidate(
        records.intents, attempt_id, v1_plan,
    )
    if (report.intent_hash != intent.payload_sha256
            or report.candidate_hash != candidate["candidate_hash"]):
        raise DelegationIntegrityError("Kilo pending recorded candidate changed")
    witness = load_bound_agent_start(
        records.intents.bridge_store.authority,
        records.intents.bridge_store.start, attempt_id,
    )
    bridge = records.intents.bridge_store.get(attempt_id)
    if bridge is None:
        raise DelegationIntegrityError("Kilo pending bridge missing")
    fake_response = build_agent_local_kilo_fake_ping_body(witness, bridge)
    try:
        event = parse_ping_pending_event(
            event_line, attempt_id=attempt_id,
            response_sha256=fake_response["sse_sha256"],
        )
    except PingPendingEventDenied as exc:
        raise DelegationIntegrityError("Kilo pending event denied") from exc
    try:
        inspect_fake_raw_peer(
            SimpleNamespace(network_id=report.network_id,
                            container_id=report.container_id),
            FakeRawPeerBinding(candidate["network"]["name"], gateway_id),
            SyntheticAcceptedPeer(event.peer_ip),
            network, receiver, gateway,
        )
    except FakeRawPeerDenied as exc:
        raise DelegationIntegrityError("Kilo pending reported peer denied") from exc
    return {
        "decision": "KILO_PENDING_REPORTED_MATCH_ONLY",
        "attempt_id": attempt_id,
        "response_sha256": fake_response["sse_sha256"],
        "request_sha256": event.body_sha256,
        "peer_qualified": False,
        "release_authorized": False,
        "receiver_executed": False,
    }
