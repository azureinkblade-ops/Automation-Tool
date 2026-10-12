"""Fake-only delegated issue-request identity preflight."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hc_agent_receiver_start_fence import fence
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_invocation_issue_preflight import preflight_agent_issue_request
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)


def issue_request(bridge):
    return ProductionInvocationAuthorizationIssueRequest(
        issue_request_id="issue-1",
        execution_request_id=bridge.execution_request_id,
        receiver_id=bridge.receiver_agent_id,
        binding_id=bridge.executor_binding_id,
        enablement_id=bridge.executor_enablement_id,
        nonce="nonce-1",
    )


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
