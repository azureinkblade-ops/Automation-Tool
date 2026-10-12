"""Fake-only delegated issue-request identity preflight."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hc_agent_receiver_start_fence import fence
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_invocation_issue_preflight import (
    build_agent_issue_request, preflight_agent_issue_request,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)


def issue_request(bridge):
    return build_agent_issue_request(bridge, requested_ttl_seconds=60)


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_exact_request_matches_existing_reservation(tmp_path, agent):
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        resolution = fake_resolution(agent)
        bridge = store.reserve(lease.attempt_id, resolution)
        assert preflight_agent_issue_request(
            store, lease.attempt_id, resolution, issue_request(bridge),
        ) == bridge
    finally:
        start.close()


def test_absent_reservation_does_not_create_one(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        request = ProductionInvocationAuthorizationIssueRequest(
            "issue-1", "caller-chosen", agent, "executor-binding-1",
            "enablement-1", "nonce-1",
        )
        with pytest.raises(DelegationIntegrityError, match="reservation absent"):
            preflight_agent_issue_request(store, lease.attempt_id, fake_resolution(agent), request)
        assert store.get(lease.attempt_id) is None
    finally:
        start.close()


@pytest.mark.parametrize("field,value", [
    ("execution_request_id", "caller-chosen"),
    ("receiver_id", "opencode-cli-agent"),
    ("binding_id", "other-binding"),
    ("enablement_id", "other-enablement"),
    ("issue_request_id", "other-issue"),
    ("nonce", "other-nonce"),
])
def test_swapped_issue_identity_denied(tmp_path, field, value):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        resolution = fake_resolution(agent)
        bridge = store.reserve(lease.attempt_id, resolution)
        with pytest.raises(DelegationIntegrityError, match="identity mismatch"):
            preflight_agent_issue_request(
                store, lease.attempt_id, resolution,
                replace(issue_request(bridge), **{field: value}),
            )
        assert store.get(lease.attempt_id) == bridge
    finally:
        start.close()


def test_issue_identity_stable_across_replay_and_ttl_conflict(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge = store.reserve(lease.attempt_id, fake_resolution(agent))
        first = issue_request(bridge)
        assert first == issue_request(bridge)
        changed_ttl = build_agent_issue_request(bridge, requested_ttl_seconds=30)
        assert changed_ttl.issue_request_id == first.issue_request_id
        assert changed_ttl.nonce == first.nonce
        assert changed_ttl.to_canonical_dict() != first.to_canonical_dict()
        with pytest.raises(DelegationIntegrityError, match="inputs denied"):
            build_agent_issue_request(bridge, requested_ttl_seconds=301)
    finally:
        start.close()


def test_cancelled_authority_denied_even_for_matching_request(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, task, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        resolution = fake_resolution(agent)
        bridge = store.reserve(lease.attempt_id, resolution)
        authority.cancel_delegation(
            task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:05Z",
        )
        with pytest.raises(DelegationIntegrityError):
            preflight_agent_issue_request(
                store, lease.attempt_id, resolution, issue_request(bridge),
            )
    finally:
        start.close()


def test_claimed_receiver_start_denied_even_for_matching_request(tmp_path):
    agent = "opencode-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        resolution = fake_resolution(agent)
        bridge = store.reserve(lease.attempt_id, resolution)
        fence(authority, start).claim(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="already claimed"):
            preflight_agent_issue_request(
                store, lease.attempt_id, resolution, issue_request(bridge),
            )
    finally:
        start.close()
