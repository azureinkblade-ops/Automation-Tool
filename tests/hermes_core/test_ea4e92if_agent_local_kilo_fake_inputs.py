"""Revised config materialization is task-bound and never launches Kilo."""

import json
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW
from tests.hermes_core.test_ea4e92ib_local_kilo_ping_intent import accepted
from tools.hermes_core.agent_local_kilo_fake_inputs import (
    prepare_agent_local_kilo_fake_inputs,
    verified_agent_local_kilo_fake_mount_sources,
)
from tools.hermes_core.agent_local_kilo_fake_launch_candidate import GATEWAY_URL
from tools.hermes_core.agent_local_kilo_ping_intent import SQLiteAgentLocalKiloPingIntentStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.local_kilo_inert_inputs import prepare_inert_inputs


def test_revised_config_is_staged_and_bound_to_reserved_attempt(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        intents.reserve(lease.attempt_id, plan)
        prepared = prepare_agent_local_kilo_fake_inputs(
            intents, lease.attempt_id, plan, tmp_path / "revised",
        )
        input_source, runtime_source = verified_agent_local_kilo_fake_mount_sources(
            intents, lease.attempt_id, plan, prepared,
        )
        assert input_source != runtime_source
        assert prepared["launch_authorized"] is False
        config = next(item for item in prepared["files"]
                      if item["input_path"].endswith("kilo.jsonc"))
        input_bytes = Path(config["input_path"]).read_bytes()
        assert input_bytes == Path(config["runtime_path"]).read_bytes()
        assert json.loads(input_bytes)["provider"]["openai-compatible"]["options"][
            "baseURL"
        ] == GATEWAY_URL
    finally:
        start.close()


def test_old_config_and_mutated_runtime_copy_deny(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        intents.reserve(lease.attempt_id, plan)
        old = prepare_inert_inputs(tmp_path / "old")
        with pytest.raises(DelegationIntegrityError, match="manifest mismatch"):
            verified_agent_local_kilo_fake_mount_sources(
                intents, lease.attempt_id, plan, old,
            )
        prepared = prepare_agent_local_kilo_fake_inputs(
            intents, lease.attempt_id, plan, tmp_path / "revised",
        )
        Path(prepared["files"][0]["runtime_path"]).write_bytes(b"changed")
        with pytest.raises(DelegationIntegrityError, match="input bytes denied"):
            verified_agent_local_kilo_fake_mount_sources(
                intents, lease.attempt_id, plan, prepared,
            )
    finally:
        start.close()


def test_cancelled_authority_denies_existing_revised_files(tmp_path):
    authority, start, task, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        intents.reserve(lease.attempt_id, plan)
        prepared = prepare_agent_local_kilo_fake_inputs(
            intents, lease.attempt_id, plan, tmp_path / "revised",
        )
        authority.cancel_delegation(
            task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:03Z",
        )
        with pytest.raises(DelegationIntegrityError, match="inactive"):
            verified_agent_local_kilo_fake_mount_sources(
                intents, lease.attempt_id, plan, prepared,
            )
    finally:
        start.close()
