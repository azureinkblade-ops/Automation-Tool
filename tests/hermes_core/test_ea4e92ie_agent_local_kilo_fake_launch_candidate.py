"""The revised fake-network candidate is plan-bound and non-launchable."""

from copy import deepcopy
import hashlib
import json

import pytest

from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW
from tests.hermes_core.test_ea4e92ib_local_kilo_ping_intent import accepted
from tools.hermes_core.agent_local_kilo_fake_launch_candidate import (
    GATEWAY_URL,
    build_agent_local_kilo_fake_launch_candidate,
)
from tools.hermes_core.agent_local_kilo_ping_intent import SQLiteAgentLocalKiloPingIntentStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.local_kilo_inert_plan import CONFIG_DIR


def test_revision_binds_reserved_plan_without_mutating_it(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        saved = intents.reserve(lease.attempt_id, plan)
        original = deepcopy(plan)
        candidate = build_agent_local_kilo_fake_launch_candidate(
            intents, lease.attempt_id, plan,
        )
        config_file = candidate["planned_files"][f"{CONFIG_DIR}/kilo.jsonc"]
        config = json.loads(config_file["content"])
        assert config["provider"]["openai-compatible"]["options"]["baseURL"] == GATEWAY_URL
        assert hashlib.sha256(config_file["content"].encode("ascii")).hexdigest() == config_file["sha256"]
        assert candidate["v1_plan_hash"] == saved.plan_hash
        assert candidate["v1_intent_payload_sha256"] == saved.payload_sha256
        assert candidate["workspace_mount"] == {
            "destination": "/work", "kind": "tmpfs",
            "uid": 65532, "gid": 65532, "mode": "0700",
        }
        assert candidate["network"]["internal"] is True
        assert candidate["network"]["gateway_url"] == GATEWAY_URL
        assert candidate["candidate_hash"] == sha256_payload({
            key: value for key, value in candidate.items() if key != "candidate_hash"
        })
        assert candidate["launch_authorized"] is False
        assert candidate["peer_qualified"] is False
        assert candidate["gateway_body_qualified"] is False
        assert plan == original
    finally:
        start.close()


def test_deterministic_revision_and_changed_v1_plan_denied(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        intents.reserve(lease.attempt_id, plan)
        first = build_agent_local_kilo_fake_launch_candidate(intents, lease.attempt_id, plan)
        assert first == build_agent_local_kilo_fake_launch_candidate(
            intents, lease.attempt_id, plan,
        )
        changed = deepcopy(plan)
        changed["argv"][-1] = "different prompt"
        with pytest.raises(DelegationIntegrityError, match="plan mismatch"):
            build_agent_local_kilo_fake_launch_candidate(
                intents, lease.attempt_id, changed,
            )
    finally:
        start.close()


def test_unreserved_attempt_denied(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        with pytest.raises(DelegationIntegrityError, match="reserved plan mismatch"):
            build_agent_local_kilo_fake_launch_candidate(
                intents, lease.attempt_id, plan,
            )
    finally:
        start.close()


def test_cancelled_authority_denies_revision(tmp_path):
    authority, start, task, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        intents.reserve(lease.attempt_id, plan)
        authority.cancel_delegation(
            task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:03Z",
        )
        with pytest.raises(DelegationIntegrityError, match="inactive"):
            build_agent_local_kilo_fake_launch_candidate(
                intents, lease.attempt_id, plan,
            )
    finally:
        start.close()
