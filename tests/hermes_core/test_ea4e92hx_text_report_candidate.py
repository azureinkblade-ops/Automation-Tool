"""Reported bytes are parsed, but never promoted to trusted capture."""

import json

import pytest

from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92hv_text_process_observation import ARGV, prepared
from tools.hermes_core.agent_result_candidate import bind_terminal_agent_candidate
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_report_candidate import (
    preview_reported_text_ping_candidate,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError


def report(tmp_path, agent, *, stdout_bytes=None, returncode=0):
    authority, start, task, lease, observations = prepared(tmp_path, agent)
    witness = load_bound_agent_start(authority, start, lease.attempt_id)
    expected = bind_terminal_agent_candidate(
        witness.bound.invocation, terminal_outcome(witness),
    )
    if stdout_bytes is None:
        stdout_bytes = (
            json.dumps({"type": "text", "text": expected.candidate_json}) + "\n"
        ).encode("utf-8")
    observations.record_start(lease.attempt_id, ARGV, owner_id="fake-owner-1", pid=1234)
    observations.record_terminal(
        lease.attempt_id, owner_id="fake-owner-1", pid=1234,
        returncode=returncode, stdout_bytes=stdout_bytes, stderr_bytes=b"",
    )
    return authority, start, task, lease, observations, expected


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_valid_report_previews_candidate_without_capture_or_delivery(tmp_path, agent):
    authority, start, task, lease, observations, expected = report(tmp_path, agent)
    try:
        assert preview_reported_text_ping_candidate(observations, lease.attempt_id) == expected
        assert capture_store(authority, start).get(lease.attempt_id) is None
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


@pytest.mark.parametrize("stdout_bytes,returncode,reason", [
    (b"\xff", 0, "UTF-8"),
    (b"not jsonl\n", 0, "JSONL"),
    (b'{"type":"error","error":{}}\n', 0, "not valid terminal text"),
    (b'{"type":"text","text":"PONG"}\n', 0, "not strict JSON"),
    (b'{"type":"text","text":"PONG"}\n', 1, "terminal absent"),
])
def test_bad_report_denies_without_publishing(tmp_path, stdout_bytes, returncode, reason):
    authority, start, task, lease, observations, _ = report(
        tmp_path, "kilo-cli-agent", stdout_bytes=stdout_bytes,
        returncode=returncode,
    )
    try:
        with pytest.raises(DelegationIntegrityError, match=reason):
            preview_reported_text_ping_candidate(observations, lease.attempt_id)
        assert capture_store(authority, start).get(lease.attempt_id) is None
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


def test_wrong_instance_hash_is_rejected(tmp_path):
    authority, start, task, lease, observations, _ = report(
        tmp_path, "opencode-cli-agent",
        stdout_bytes=json.dumps({
            "type": "text",
            "text": json.dumps({
                "schema_version": "1", "outcome": "SUCCEEDED",
                "result_payload": {
                    "task_input_hash": "0" * 64,
                    "receiver_receipt_hash": "0" * 64,
                    "statement": "opencode-cli-agent:PING_OK",
                },
                "output_manifest": [],
                "evidence_manifest": [{
                    "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
                    "sha256": "0" * 64,
                }],
                "error_code": None, "error_summary": None,
            }),
        }).encode("utf-8"),
    )
    try:
        with pytest.raises(DelegationIntegrityError, match="ping payload"):
            preview_reported_text_ping_candidate(observations, lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()
