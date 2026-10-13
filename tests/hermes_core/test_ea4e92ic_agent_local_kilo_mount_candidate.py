"""Fake-only binding of prepared config sources to a reserved delegated plan."""

from copy import deepcopy
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ib_local_kilo_ping_intent import accepted
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW
from tools.hermes_core.agent_local_kilo_mount_candidate import (
    build_agent_local_kilo_mount_candidate,
)
from tools.hermes_core.agent_local_kilo_ping_intent import SQLiteAgentLocalKiloPingIntentStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.local_kilo_inert_inputs import prepare_inert_inputs


def test_reserved_plan_binds_separate_reviewed_and_runtime_sources(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        intent = intents.reserve(lease.attempt_id, plan)
        prepared = prepare_inert_inputs(tmp_path / "inputs")
        result = build_agent_local_kilo_mount_candidate(
            intents, lease.attempt_id, plan, prepared,
        )
        assert result["plan_hash"] == intent.plan_hash
        assert result["intent_payload_sha256"] == intent.payload_sha256
        assert result["mounts"] == [
            {"source": str(tmp_path / "inputs" / "input"),
             "destination": "/reviewed-input", "read_only": True},
            {"source": str(tmp_path / "inputs" / "runtime"),
             "destination": "/tmp/kilo-home", "read_only": False},
        ]
        assert result["effective_mounts_checked"] is False
        assert result["launch_authorized"] is False
    finally:
        start.close()


def test_changed_plan_and_prepared_bytes_deny(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        intents.reserve(lease.attempt_id, plan)
        prepared = prepare_inert_inputs(tmp_path / "inputs")
        changed = deepcopy(plan)
        changed["argv"][-1] = "different prompt"
        with pytest.raises(DelegationIntegrityError, match="plan mismatch"):
            build_agent_local_kilo_mount_candidate(
                intents, lease.attempt_id, changed, prepared,
            )
        Path(prepared["files"][0]["runtime_path"]).write_bytes(b"changed")
        with pytest.raises(DelegationIntegrityError, match="prepared inputs denied"):
            build_agent_local_kilo_mount_candidate(
                intents, lease.attempt_id, plan, prepared,
            )
    finally:
        start.close()


def test_unreserved_plan_denies(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        prepared = prepare_inert_inputs(tmp_path / "inputs")
        with pytest.raises(DelegationIntegrityError, match="reserved plan mismatch"):
            build_agent_local_kilo_mount_candidate(
                intents, lease.attempt_id, plan, prepared,
            )
    finally:
        start.close()
