"""Recorded fake container stdout can only produce a preview candidate."""

import sqlite3

import pytest

from tests.hermes_core.durable_auth_test_support import qualification_store
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hj_agent_delegated_claim_owner import owner
from tests.hermes_core.test_ea4e92ik_agent_local_kilo_container_preview import (
    preview_fixture,
)
from tests.hermes_core.test_ea4e92ij_agent_local_kilo_container_record import NETWORK_ID
from tools.hermes_core.agent_local_kilo_container_observation import (
    SQLiteAgentLocalKiloContainerObservationStore,
)
from tools.hermes_core.agent_local_kilo_container_preview import (
    preview_recorded_kilo_container_ping,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError


def recorded(tmp_path, *, exit_code=0):
    start, records, report, expected, stdout = preview_fixture(tmp_path)
    current = owner(
        records.intents.bridge_store.authority, start,
        qualification_store(tmp_path),
    )
    resolution = fake_resolution("kilo-cli-agent")
    issued = current.issue(report.attempt_id, resolution)
    assert issued.policy_decision == "ALLOW"
    assert current.claim_and_fence(
        report.attempt_id, resolution, issued.authorization,
    ).status == "FENCED"
    observations = SQLiteAgentLocalKiloContainerObservationStore(
        records, current.fence_store, clock=lambda: NOW,
    )
    observations.record_start(
        report.attempt_id, container_id=report.container_id,
        network_id=NETWORK_ID, owner_id="fake-owner",
    )
    observations.record_terminal(
        report.attempt_id, container_id=report.container_id,
        owner_id="fake-owner", exit_code=exit_code,
        stdout_bytes=stdout, stderr_bytes=b"",
    )
    return start, records, report, expected, observations


def test_recorded_terminal_previews_without_mailbox_delivery(tmp_path):
    start, records, report, expected, observations = recorded(tmp_path)
    try:
        assert preview_recorded_kilo_container_ping(
            observations, report.attempt_id,
        ) == expected
        witness = load_bound_agent_start(
            records.intents.bridge_store.authority,
            records.intents.bridge_store.start, report.attempt_id,
        )
        assert records.intents.bridge_store.authority.list_mailbox(
            witness.task.originator_agent_id,
        ) == []
    finally:
        start.close()


def test_failed_terminal_cannot_preview(tmp_path):
    start, _, report, _, observations = recorded(tmp_path, exit_code=1)
    try:
        with pytest.raises(DelegationIntegrityError, match="terminal denied"):
            preview_recorded_kilo_container_ping(observations, report.attempt_id)
    finally:
        start.close()


def test_terminal_tamper_denies_preview(tmp_path):
    start, records, report, _, observations = recorded(tmp_path)
    try:
        with sqlite3.connect(records.intents.bridge_store.authority.path) as conn:
            conn.execute(
                "UPDATE agent_local_kilo_container_terminals SET stdout_bytes=? "
                "WHERE attempt_id=?", (b"forged", report.attempt_id),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            preview_recorded_kilo_container_ping(observations, report.attempt_id)
    finally:
        start.close()


def test_absent_terminal_denies_preview(tmp_path):
    start, records, report, _, _ = preview_fixture(tmp_path)
    try:
        current = owner(
            records.intents.bridge_store.authority, start,
            qualification_store(tmp_path),
        )
        observations = SQLiteAgentLocalKiloContainerObservationStore(
            records, current.fence_store, clock=lambda: NOW,
        )
        with pytest.raises(DelegationIntegrityError, match="terminal absent"):
            preview_recorded_kilo_container_ping(observations, report.attempt_id)
    finally:
        start.close()
