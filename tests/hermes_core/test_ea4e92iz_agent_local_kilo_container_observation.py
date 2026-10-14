"""Fake-only durable Kilo container observations; no Docker calls."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.hermes_core.durable_auth_test_support import qualification_store
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hj_agent_delegated_claim_owner import owner
from tests.hermes_core.test_ea4e92ij_agent_local_kilo_container_record import (
    CONTAINER_ID, NETWORK_ID, observed,
)
from tools.hermes_core.agent_local_kilo_container_observation import (
    SQLiteAgentLocalKiloContainerObservationStore,
)
from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_local_kilo_ping_intent import SQLiteAgentLocalKiloPingIntentStore
from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.agent_start_witness import load_bound_agent_start


def fixture(tmp_path, *, fenced=True):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    created = SQLiteAgentLocalKiloContainerRecordStore(intents)
    created.record(attempt, plan, prepared, container, image)
    current = owner(
        intents.bridge_store.authority, start, qualification_store(tmp_path),
    )
    if fenced:
        resolution = fake_resolution("kilo-cli-agent")
        issued = current.issue(attempt, resolution)
        assert issued.policy_decision == "ALLOW"
        result = current.claim_and_fence(attempt, resolution, issued.authorization)
        assert result.status == "FENCED"
    store = SQLiteAgentLocalKiloContainerObservationStore(
        created, current.fence_store, clock=lambda: NOW,
    )
    return start, intents, attempt, store


def test_start_and_terminal_replay_survive_reopen(tmp_path):
    start, intents, attempt, store = fixture(tmp_path)
    try:
        saved = store.record_start(
            attempt, container_id=CONTAINER_ID, network_id=NETWORK_ID,
            owner_id="fake-owner",
        )
        assert saved.container_id == CONTAINER_ID
        assert saved.network_id == NETWORK_ID
        with pytest.raises(DelegationIntegrityError, match="already recorded"):
            store.record_start(
                attempt, container_id=CONTAINER_ID, network_id=NETWORK_ID,
                owner_id="fake-owner",
            )
        terminal = store.record_terminal(
            attempt, container_id=CONTAINER_ID, owner_id="fake-owner",
            exit_code=0, stdout_bytes=b"fake", stderr_bytes=b"",
        )
        assert store.get_terminal(attempt) == terminal
        assert store.record_terminal(
            attempt, container_id=CONTAINER_ID, owner_id="fake-owner",
            exit_code=0, stdout_bytes=b"fake", stderr_bytes=b"",
        ) == terminal
        with pytest.raises(DelegationIntegrityError, match="divergent"):
            store.record_terminal(
                attempt, container_id=CONTAINER_ID, owner_id="fake-owner",
                exit_code=1, stdout_bytes=b"fake", stderr_bytes=b"",
            )
        reopened = SQLiteAgentLocalKiloContainerObservationStore(
            store.created, store.fences, clock=lambda: NOW,
        )
        assert reopened.get_start(attempt) == saved
        assert reopened.get_terminal(attempt) == terminal
    finally:
        start.close()


def test_start_requires_fence(tmp_path):
    start, _, attempt, store = fixture(tmp_path, fenced=False)
    try:
        with pytest.raises(DelegationIntegrityError, match="authority mismatch"):
            store.record_start(
                attempt, container_id=CONTAINER_ID, network_id=NETWORK_ID,
                owner_id="fake-owner",
            )
        assert store.get_start(attempt) is None
    finally:
        start.close()


@pytest.mark.parametrize("container_id,network_id,owner_id", [
    ("c" * 64, NETWORK_ID, "fake-owner"),
    (CONTAINER_ID, "d" * 64, "fake-owner"),
    (CONTAINER_ID, NETWORK_ID, ""),
])
def test_swapped_start_identity_denied(tmp_path, container_id, network_id, owner_id):
    start, _, attempt, store = fixture(tmp_path)
    try:
        with pytest.raises(DelegationIntegrityError):
            store.record_start(
                attempt, container_id=container_id, network_id=network_id,
                owner_id=owner_id,
            )
        assert store.get_start(attempt) is None
    finally:
        start.close()


def test_terminal_owner_and_size_denied(tmp_path):
    start, _, attempt, store = fixture(tmp_path)
    try:
        store.record_start(
            attempt, container_id=CONTAINER_ID, network_id=NETWORK_ID,
            owner_id="fake-owner",
        )
        with pytest.raises(DelegationIntegrityError, match="owner mismatch"):
            store.record_terminal(
                attempt, container_id="c" * 64, owner_id="fake-owner",
                exit_code=0, stdout_bytes=b"", stderr_bytes=b"",
            )
        with pytest.raises(DelegationIntegrityError, match="data denied"):
            store.record_terminal(
                attempt, container_id=CONTAINER_ID, owner_id="fake-owner",
                exit_code=0, stdout_bytes=b"x" * (4 * 1024 * 1024 + 1),
                stderr_bytes=b"",
            )
        assert store.get_terminal(attempt) is None
    finally:
        start.close()


def test_terminal_remains_readable_after_cancellation(tmp_path):
    start, intents, attempt, store = fixture(tmp_path)
    try:
        saved = store.record_start(
            attempt, container_id=CONTAINER_ID, network_id=NETWORK_ID,
            owner_id="fake-owner",
        )
        witness = load_bound_agent_start(
            intents.bridge_store.authority, start, attempt,
        )
        intents.bridge_store.authority.cancel_delegation(
            witness.task.delegation_id, reason="operator",
            cancelled_at="2026-08-27T12:05:03Z",
        )
        terminal = store.record_terminal(
            attempt, container_id=CONTAINER_ID, owner_id="fake-owner",
            exit_code=137, stdout_bytes=b"", stderr_bytes=b"cancelled",
        )
        assert store.get_start(attempt) == saved
        assert store.get_terminal(attempt) == terminal
    finally:
        start.close()


def test_cancellation_before_start_denies_report(tmp_path):
    start, intents, attempt, store = fixture(tmp_path)
    try:
        witness = load_bound_agent_start(
            intents.bridge_store.authority, start, attempt,
        )
        intents.bridge_store.authority.cancel_delegation(
            witness.task.delegation_id, reason="operator",
            cancelled_at="2026-08-27T12:05:03Z",
        )
        with pytest.raises(DelegationIntegrityError, match="inactive"):
            store.record_start(
                attempt, container_id=CONTAINER_ID, network_id=NETWORK_ID,
                owner_id="fake-owner",
            )
        assert store.get_start(attempt) is None
    finally:
        start.close()


def test_competing_start_writers_account_once(tmp_path):
    start, intents, attempt, store = fixture(tmp_path)
    try:
        def write(_):
            authority = SQLiteDelegationStore(intents.bridge_store.authority.path)
            local_start = SQLiteExecutionStartStore(start._db_path)
            try:
                bridges = SQLiteAgentInvocationBridgeStore(
                    authority, local_start, clock=lambda: NOW,
                )
                local_intents = SQLiteAgentLocalKiloPingIntentStore(
                    bridges, clock=lambda: NOW,
                )
                created = SQLiteAgentLocalKiloContainerRecordStore(local_intents)
                fences = SQLiteAgentReceiverStartFenceStore(
                    authority, local_start, clock=lambda: NOW,
                )
                local_store = SQLiteAgentLocalKiloContainerObservationStore(
                    created, fences, clock=lambda: NOW,
                )
                return local_store.record_start(
                    attempt, container_id=CONTAINER_ID, network_id=NETWORK_ID,
                    owner_id="fake-owner",
                )
            except DelegationIntegrityError as exc:
                return str(exc)
            finally:
                local_start.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, range(2)))
        assert sum(not isinstance(item, str) for item in results) == 1
        assert "Kilo container start already recorded" in results
    finally:
        start.close()


def test_created_record_tamper_invalidates_start(tmp_path):
    start, intents, attempt, store = fixture(tmp_path)
    try:
        store.record_start(
            attempt, container_id=CONTAINER_ID, network_id=NETWORK_ID,
            owner_id="fake-owner",
        )
        with sqlite3.connect(intents.bridge_store.authority.path) as conn:
            conn.execute(
                "UPDATE agent_local_kilo_created_reports SET payload_sha256=? "
                "WHERE attempt_id=?", ("0" * 64, attempt),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            store.get_start(attempt)
    finally:
        start.close()


def test_tampered_start_and_terminal_denied(tmp_path):
    start, intents, attempt, store = fixture(tmp_path)
    try:
        store.record_start(
            attempt, container_id=CONTAINER_ID, network_id=NETWORK_ID,
            owner_id="fake-owner",
        )
        store.record_terminal(
            attempt, container_id=CONTAINER_ID, owner_id="fake-owner",
            exit_code=0, stdout_bytes=b"fake", stderr_bytes=b"",
        )
        with sqlite3.connect(intents.bridge_store.authority.path) as conn:
            conn.execute(
                "UPDATE agent_local_kilo_container_terminals SET stdout_bytes=? "
                "WHERE attempt_id=?", (b"other", attempt),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            store.get_terminal(attempt)
        with sqlite3.connect(intents.bridge_store.authority.path) as conn:
            conn.execute(
                "UPDATE agent_local_kilo_container_starts SET canonical_payload='{}' "
                "WHERE attempt_id=?", (attempt,),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            store.get_start(attempt)
    finally:
        start.close()
