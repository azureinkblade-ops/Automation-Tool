"""Fake-only durable issue/claim/fence owner; no process or model calls."""

from dataclasses import replace

import pytest

from tests.hermes_core.durable_auth_test_support import qualification_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hc_agent_receiver_start_fence import fence
from tools.hermes_core.agent_delegated_claim_owner import AgentDelegatedClaimOwner
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.production_executor_binding import BindingClock


def owner(authority, start, auth_store):
    return AgentDelegatedClaimOwner(
        SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW),
        fence(authority, start), auth_store,
        clock=BindingClock(now=NOW.isoformat()),
    )


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_exact_issue_claim_fence_and_restart_never_restarts(tmp_path, agent):
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        issued = current.issue(lease.attempt_id, resolution)
        assert issued.policy_decision == "ALLOW"
        assert current.issue(lease.attempt_id, resolution).idempotent_replay
        claimed = current.claim_and_fence(
            lease.attempt_id, resolution, issued.authorization,
        )
        assert claimed.status == "FENCED"
        assert claimed.reason == "NO_RECEIVER_STARTED"
        assert claimed.fence_hash == current.fence_store.get(lease.attempt_id).claim_hash
        assert auth_store.inspect(issued.authorization.to_canonical_dict()).consumed
        reopened_auth_store = DurableInvocationAuthorizationStore(
            auth_store.path, anchor_path=auth_store.anchor_path,
        )
        reopened = owner(authority, start, reopened_auth_store)
        again = reopened.claim_and_fence(
            lease.attempt_id, resolution, issued.authorization,
        )
        assert again.status == "UNKNOWN"
        assert auth_store.consumed_count() == 1
    finally:
        start.close()


def test_failed_fence_after_consumption_stays_unknown_on_restart(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        auth = current.issue(lease.attempt_id, resolution).authorization

        def fail_fence(_):
            raise RuntimeError("injected pre-fence failure")

        current.fence_store.claim = fail_fence
        first = current.claim_and_fence(lease.attempt_id, resolution, auth)
        assert first.status == "UNKNOWN"
        assert auth_store.inspect(auth.to_canonical_dict()).consumed
        assert current.fence_store.get(lease.attempt_id) is None

        reopened_store = DurableInvocationAuthorizationStore(
            auth_store.path, anchor_path=auth_store.anchor_path,
        )
        reopened = owner(authority, start, reopened_store)
        second = reopened.claim_and_fence(lease.attempt_id, resolution, auth)
        assert second.status == "UNKNOWN"
        assert reopened.fence_store.get(lease.attempt_id) is None
        assert reopened_store.consumed_count() == 1
    finally:
        start.close()


def test_cancellation_between_claim_and_fence_is_unknown(tmp_path):
    agent = "opencode-cli-agent"
    authority, start, task, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        auth = current.issue(lease.attempt_id, resolution).authorization
        original_claim = current.fence_store.claim

        def cancel_then_fence(attempt_id):
            authority.cancel_delegation(
                task.delegation_id, reason="operator",
                cancelled_at="2026-08-27T12:05:05Z",
            )
            return original_claim(attempt_id)

        current.fence_store.claim = cancel_then_fence
        result = current.claim_and_fence(lease.attempt_id, resolution, auth)
        assert result.status == "UNKNOWN"
        assert auth_store.inspect(auth.to_canonical_dict()).consumed
        assert current.fence_store.get(lease.attempt_id) is None
    finally:
        start.close()


@pytest.mark.parametrize("action", ["cancel", "revoke"])
def test_lost_authority_before_claim_cannot_consume_or_fence(tmp_path, action):
    agent = "kilo-cli-agent"
    authority, start, task, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        issued = current.issue(lease.attempt_id, resolution)
        if action == "cancel":
            authority.cancel_delegation(
                task.delegation_id, reason="operator",
                cancelled_at="2026-08-27T12:05:05Z",
            )
        else:
            authority.revoke_lease(
                lease.lease_id, reason="operator",
                revoked_at="2026-08-27T12:05:05Z",
            )
        result = current.claim_and_fence(
            lease.attempt_id, resolution, issued.authorization,
        )
        assert result.status == "DENIED"
        assert not auth_store.inspect(issued.authorization.to_canonical_dict()).consumed
        assert current.fence_store.get(lease.attempt_id) is None
    finally:
        start.close()


def test_swapped_authorization_denied_without_consumption(tmp_path):
    agent = "opencode-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        auth = current.issue(lease.attempt_id, resolution).authorization
        swapped = replace(auth, execution_request_id="caller-chosen")
        result = current.claim_and_fence(lease.attempt_id, resolution, swapped)
        assert result.status in {"DENIED", "UNKNOWN"}
        assert not auth_store.inspect(auth.to_canonical_dict()).consumed
        assert current.fence_store.get(lease.attempt_id) is None
    finally:
        start.close()


def test_changed_ttl_cannot_create_second_authorization(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        first = current.issue(lease.attempt_id, resolution)
        changed = AgentDelegatedClaimOwner(
            current.bridge_store, current.fence_store, auth_store,
            clock=BindingClock(now=NOW.isoformat()), ttl_seconds=30,
        )
        second = changed.issue(lease.attempt_id, resolution)
        assert first.policy_decision == "ALLOW"
        assert (second.policy_decision, second.policy_reason) == (
            "DENY", "ISSUE_REQUEST_ID_COLLISION",
        )
        assert auth_store.count() == 1
    finally:
        start.close()


def test_alternate_authorization_store_cannot_issue_or_claim(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        pinned = qualification_store(tmp_path)
        alternate = qualification_store(tmp_path, "alternate-authorization.sqlite3")
        current = owner(authority, start, pinned)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        auth = current.issue(lease.attempt_id, resolution).authorization
        other = owner(authority, start, alternate)
        with pytest.raises(DelegationIntegrityError, match="store identity mismatch"):
            other.issue(lease.attempt_id, resolution)
        assert alternate.count() == 0
        assert other.claim_and_fence(
            lease.attempt_id, resolution, auth,
        ).status == "DENIED"
        assert current.fence_store.get(lease.attempt_id) is None
    finally:
        start.close()


def test_owner_clock_denies_expired_lease_despite_stale_store_clocks(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        stale_bridge = SQLiteAgentInvocationBridgeStore(
            authority, start, clock=lambda: NOW,
        )
        resolution = fake_resolution(agent)
        stale_bridge.reserve(lease.attempt_id, resolution)
        expired = AgentDelegatedClaimOwner(
            stale_bridge, fence(authority, start), auth_store,
            clock=BindingClock(now="2027-08-27T12:05:04+00:00"),
        )
        with pytest.raises(DelegationIntegrityError, match="outside lease window"):
            expired.issue(lease.attempt_id, resolution)
        assert auth_store.count() == 0
        assert expired.fence_store.get(lease.attempt_id) is None
    finally:
        start.close()
