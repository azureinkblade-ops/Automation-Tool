"""Fake-only durable created-container reports; no Docker is used."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92ig_agent_local_kilo_fake_prestart import fixture
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW
from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_local_kilo_ping_intent import SQLiteAgentLocalKiloPingIntentStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


CONTAINER_ID = "a" * 64
NETWORK_ID = "b" * 64


def observed(tmp_path):
    start, intents, attempt, plan, prepared, container, image = fixture(tmp_path)
    container["Id"] = CONTAINER_ID
    only_network = next(iter(container["NetworkSettings"]["Networks"].values()))
    only_network["NetworkID"] = NETWORK_ID
    return start, intents, attempt, plan, prepared, container, image


def test_record_persists_identity_and_denies_replay(tmp_path):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    try:
        records = SQLiteAgentLocalKiloContainerRecordStore(intents)
        saved = records.record(attempt, plan, prepared, container, image)
        assert saved.container_id == CONTAINER_ID
        assert saved.network_id == NETWORK_ID
        assert saved.launch_authorized is False
        assert SQLiteAgentLocalKiloContainerRecordStore(intents).get(attempt) == saved
        with pytest.raises(DelegationIntegrityError, match="already recorded"):
            records.record(attempt, plan, prepared, container, image)
    finally:
        start.close()


@pytest.mark.parametrize("change", [
    lambda c, i: c.update(Id="bad"),
    lambda c, i: next(iter(c["NetworkSettings"]["Networks"].values())).update(NetworkID="bad"),
    lambda c, i: c["Config"].update(Cmd=["other"]),
    lambda c, i: i.update(Id="sha256:" + "0" * 64),
    lambda c, i: c["Mounts"][0].update(RW=True),
])
def test_wrong_report_denied_without_row(tmp_path, change):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    try:
        records = SQLiteAgentLocalKiloContainerRecordStore(intents)
        changed_container, changed_image = deepcopy(container), deepcopy(image)
        change(changed_container, changed_image)
        with pytest.raises(DelegationIntegrityError):
            records.record(attempt, plan, prepared, changed_container, changed_image)
        assert records.get(attempt) is None
    finally:
        start.close()


def test_cancelled_authority_denies_but_saved_report_remains_readable(tmp_path):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    try:
        records = SQLiteAgentLocalKiloContainerRecordStore(intents)
        saved = records.record(attempt, plan, prepared, container, image)
        witness = load_bound_agent_start(
            intents.bridge_store.authority, intents.bridge_store.start, attempt,
        )
        intents.bridge_store.authority.cancel_delegation(
            witness.task.delegation_id, reason="operator",
            cancelled_at="2026-08-27T12:05:03Z",
        )
        assert records.get(attempt) == saved
        with pytest.raises(DelegationIntegrityError):
            records.record(attempt, plan, prepared, container, image)
    finally:
        start.close()


def test_row_tamper_denied(tmp_path):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    try:
        records = SQLiteAgentLocalKiloContainerRecordStore(intents)
        records.record(attempt, plan, prepared, container, image)
        with sqlite3.connect(intents.bridge_store.authority.path) as conn:
            conn.execute(
                "UPDATE agent_local_kilo_created_reports SET canonical_payload='{}' "
                "WHERE attempt_id=?", (attempt,),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            records.get(attempt)
    finally:
        start.close()


def test_identity_column_tamper_denied(tmp_path):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    try:
        records = SQLiteAgentLocalKiloContainerRecordStore(intents)
        records.record(attempt, plan, prepared, container, image)
        with sqlite3.connect(intents.bridge_store.authority.path) as conn:
            conn.execute(
                "UPDATE agent_local_kilo_created_reports SET container_id=? "
                "WHERE attempt_id=?", ("c" * 64, attempt),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            records.get(attempt)
    finally:
        start.close()


def test_competing_writers_record_once(tmp_path):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    try:
        def write():
            authority = SQLiteDelegationStore(intents.bridge_store.authority.path)
            local_start = SQLiteExecutionStartStore(start._db_path)
            try:
                bridges = SQLiteAgentInvocationBridgeStore(
                    authority, local_start, clock=lambda: NOW,
                )
                local_intents = SQLiteAgentLocalKiloPingIntentStore(
                    bridges, clock=lambda: NOW,
                )
                records = SQLiteAgentLocalKiloContainerRecordStore(local_intents)
                return records.record(attempt, plan, prepared, container, image)
            except DelegationIntegrityError as exc:
                return str(exc)
            finally:
                local_start.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: write(), range(2)))
        assert sum(not isinstance(item, str) for item in results) == 1
        assert "Kilo created report already recorded" in results
    finally:
        start.close()
