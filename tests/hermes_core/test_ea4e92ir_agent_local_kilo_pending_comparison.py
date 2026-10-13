"""Synthetic pending-event and reported-peer comparison; no Docker calls."""

from copy import deepcopy
import json

import pytest

from tests.hermes_core.test_ea4e92ij_agent_local_kilo_container_record import observed
from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_local_kilo_fake_launch_candidate import (
    build_agent_local_kilo_fake_launch_candidate,
)
from tools.hermes_core.agent_local_kilo_fake_ping_body import (
    build_agent_local_kilo_fake_ping_body,
)
from tools.hermes_core.agent_local_kilo_pending_comparison import (
    compare_reported_kilo_ping_pending,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError


GATEWAY_ID = "c" * 64


def fixture(tmp_path):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    records = SQLiteAgentLocalKiloContainerRecordStore(intents)
    report = records.record(attempt, plan, prepared, container, image)
    candidate = build_agent_local_kilo_fake_launch_candidate(intents, attempt, plan)
    witness = load_bound_agent_start(intents.bridge_store.authority, start, attempt)
    fake = build_agent_local_kilo_fake_ping_body(
        witness, intents.bridge_store.get(attempt),
    )
    network_name = candidate["network"]["name"]
    network = {
        "Id": report.network_id, "Name": network_name,
        "Driver": "bridge", "Internal": True, "EnableIPv6": False,
        "Containers": {
            report.container_id: {"IPv4Address": "172.20.0.2/16"},
            GATEWAY_ID: {"IPv4Address": "172.20.0.3/16"},
        },
    }

    def running(identity, ip):
        return {
            "Id": identity, "State": {"Running": True},
            "HostConfig": {"NetworkMode": network_name,
                           "PublishAllPorts": False, "PortBindings": {}},
            "NetworkSettings": {
                "Networks": {network_name: {
                    "NetworkID": report.network_id, "IPAddress": ip,
                }},
                "Ports": {"8181/tcp": None},
            },
        }

    event = {
        "event": "FAKE_PING_REQUEST_PENDING",
        "attempt_id": attempt,
        "response_sha256": fake["sse_sha256"],
        "peer": "172.20.0.2",
        "body_bytes": 123,
        "body_sha256": "d" * 64,
    }
    values = {
        "records": records, "attempt_id": attempt,
        "container_id": report.container_id, "v1_plan": plan,
        "event_line": (json.dumps(event, separators=(",", ":")) + "\n").encode(),
        "gateway_id": GATEWAY_ID, "network": network,
        "receiver": running(report.container_id, "172.20.0.2"),
        "gateway": running(GATEWAY_ID, "172.20.0.3"),
    }
    return start, values, event


def test_matching_report_remains_non_authoritative(tmp_path):
    start, values, event = fixture(tmp_path)
    try:
        result = compare_reported_kilo_ping_pending(**values)
        assert result["decision"] == "KILO_PENDING_REPORTED_MATCH_ONLY"
        assert result["attempt_id"] == event["attempt_id"]
        assert result["response_sha256"] == event["response_sha256"]
        assert result["request_sha256"] == event["body_sha256"]
        assert result["peer_qualified"] is False
        assert result["release_authorized"] is False
        assert result["receiver_executed"] is False
    finally:
        start.close()


@pytest.mark.parametrize("change", [
    lambda values, event: values.update(container_id="0" * 64),
    lambda values, event: event.update(attempt_id="other-attempt"),
    lambda values, event: event.update(response_sha256="0" * 64),
    lambda values, event: values["network"]["Containers"].update({
        "e" * 64: {"IPv4Address": "172.20.0.4/16"},
    }),
    lambda values, event: values["receiver"]["State"].update(Running=False),
    lambda values, event: event.update(peer="172.20.0.3"),
])
def test_divergent_event_or_peer_denied(tmp_path, change):
    start, original, original_event = fixture(tmp_path)
    try:
        values, event = original.copy(), deepcopy(original_event)
        for key in ("network", "receiver", "gateway"):
            values[key] = deepcopy(original[key])
        change(values, event)
        values["event_line"] = (json.dumps(event, separators=(",", ":")) + "\n").encode()
        with pytest.raises(DelegationIntegrityError):
            compare_reported_kilo_ping_pending(**values)
    finally:
        start.close()
