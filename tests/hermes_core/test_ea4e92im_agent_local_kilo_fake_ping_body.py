"""Synthetic task-bound response bytes; no gateway, receiver, or model."""

import hashlib
import json
from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92ib_local_kilo_ping_intent import accepted
from tools.hermes_core.agent_local_kilo_fake_ping_body import (
    build_agent_local_kilo_fake_ping_body,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError


def test_response_text_is_attempt_bound_and_not_old_fixed_token(tmp_path):
    _, start, task, lease, bridges, _ = accepted(tmp_path)
    try:
        witness = load_bound_agent_start(bridges.authority, start, lease.attempt_id)
        bridge = bridges.get(lease.attempt_id)
        response = build_agent_local_kilo_fake_ping_body(witness, bridge)
        body = json.loads(response["candidate_json"])
        assert body["result_payload"]["task_input_hash"] == task.task_input_hash
        assert body["result_payload"]["receiver_receipt_hash"] == witness.receipt.artifact_hash
        assert response["candidate_json"] != "EA4E_INERT_OK"
        assert response["sse_sha256"] == hashlib.sha256(response["sse_bytes"]).hexdigest()
        assert response["sse_bytes"].endswith(b"data: [DONE]\n\n")
        event = json.loads(response["sse_bytes"].split(b"\n\n", 1)[0][6:])
        assert event["choices"][0]["delta"]["content"] == response["candidate_json"]
        assert response["gateway_qualified"] is False
        assert response["launch_authorized"] is False
    finally:
        start.close()


def test_divergent_bridge_denied(tmp_path):
    _, start, _, lease, bridges, _ = accepted(tmp_path)
    try:
        witness = load_bound_agent_start(bridges.authority, start, lease.attempt_id)
        bridge = bridges.get(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError):
            build_agent_local_kilo_fake_ping_body(
                witness, replace(bridge, attempt_id="different"),
            )
    finally:
        start.close()
