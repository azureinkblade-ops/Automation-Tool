"""Synthetic Kilo container stdout preview; no receiver or result delivery."""

import json

import pytest

from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92ij_agent_local_kilo_container_record import observed
from tools.hermes_core.agent_local_kilo_container_preview import (
    preview_reported_kilo_container_ping,
)
from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_result_candidate import bind_terminal_agent_candidate
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError


def preview_fixture(tmp_path):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    records = SQLiteAgentLocalKiloContainerRecordStore(intents)
    report = records.record(attempt, plan, prepared, container, image)
    witness = load_bound_agent_start(
        intents.bridge_store.authority, start, attempt,
    )
    expected = bind_terminal_agent_candidate(
        witness.bound.invocation, terminal_outcome(witness),
    )
    stdout = (json.dumps({"type": "text", "text": expected.candidate_json}) + "\n").encode()
    return start, records, report, expected, stdout


def test_reported_stdout_previews_instance_bound_candidate_only(tmp_path):
    start, records, report, expected, stdout = preview_fixture(tmp_path)
    try:
        candidate = preview_reported_kilo_container_ping(
            records, report.attempt_id, report.container_id,
            returncode=0, stdout_bytes=stdout,
        )
        assert candidate == expected
        assert report.launch_authorized is False
        witness = load_bound_agent_start(
            records.intents.bridge_store.authority,
            records.intents.bridge_store.start, report.attempt_id,
        )
        assert records.intents.bridge_store.authority.list_mailbox(
            witness.task.originator_agent_id,
        ) == []
    finally:
        start.close()


@pytest.mark.parametrize("container_id,code,stdout,reason", [
    ("wrong", 0, b"", "identity mismatch"),
    ("valid", 1, b"", "terminal denied"),
    ("valid", 0, b"\xff", "UTF-8"),
    ("valid", 0, b"not jsonl", "JSONL"),
    ("valid", 0, b'{"type":"text","text":"PONG"}\n', "strict JSON"),
])
def test_untrusted_reported_bytes_deny(tmp_path, container_id, code, stdout, reason):
    start, records, report, _, _ = preview_fixture(tmp_path)
    try:
        with pytest.raises(DelegationIntegrityError, match=reason):
            preview_reported_kilo_container_ping(
                records, report.attempt_id,
                report.container_id if container_id == "valid" else container_id,
                returncode=code, stdout_bytes=stdout,
            )
    finally:
        start.close()
