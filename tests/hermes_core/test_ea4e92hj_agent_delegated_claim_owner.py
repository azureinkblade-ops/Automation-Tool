"""Fake-only durable issue/claim/fence owner; no process or model calls."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3

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
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


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


def test_independent_concurrent_claimers_create_one_consumption_and_fence(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        initial = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        initial.bridge_store.reserve(lease.attempt_id, resolution)
        auth = initial.issue(lease.attempt_id, resolution).authorization
        barrier = Barrier(2)

        def claim_once():
            independent_start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
            try:
                independent = owner(authority, independent_start, auth_store)
                barrier.wait(timeout=5)
                return independent.claim_and_fence(
                    lease.attempt_id, resolution, auth,
                )
            finally:
                independent_start.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: claim_once(), range(2)))
        assert sorted([first.status, second.status]) == ["FENCED", "UNKNOWN"]
        assert auth_store.consumed_count() == 1
        assert initial.fence_store.get(lease.attempt_id) is not None
    finally:
        start.close()


def test_precommit_authorization_failure_is_sticky_unknown(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        auth = current.issue(lease.attempt_id, resolution).authorization

        def fail_before_commit(_):
            raise RuntimeError("injected pre-commit failure")

        auth_store._before_claim_commit = fail_before_commit
        first = current.claim_and_fence(lease.attempt_id, resolution, auth)
        assert first.status == "UNKNOWN"
        assert not auth_store.inspect(auth.to_canonical_dict()).consumed
        assert current.fence_store.get(lease.attempt_id) is None
        assert current._claim_intent_exists(lease.attempt_id)

        del auth_store._before_claim_commit
        reopened_store = DurableInvocationAuthorizationStore(
            auth_store.path, anchor_path=auth_store.anchor_path,
        )
        reopened = owner(authority, start, reopened_store)
        second = reopened.claim_and_fence(lease.attempt_id, resolution, auth)
        assert second.status == "UNKNOWN"
        assert not reopened_store.inspect(auth.to_canonical_dict()).consumed
        assert reopened.fence_store.get(lease.attempt_id) is None
        with pytest.raises(DelegationIntegrityError, match="claim intent"):
            reopened.issue(lease.attempt_id, resolution)
    finally:
        start.close()


def test_post_database_pre_anchor_failure_is_sticky_unknown(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        auth = current.issue(lease.attempt_id, resolution).authorization

        def fail_before_anchor():
            raise RuntimeError("injected post-database failure")

        auth_store._after_database_commit_before_anchor = fail_before_anchor
        first = current.claim_and_fence(lease.attempt_id, resolution, auth)
        assert first.status == "UNKNOWN"
        assert current._claim_intent_exists(lease.attempt_id)
        assert current.fence_store.get(lease.attempt_id) is None
        with sqlite3.connect(auth_store.path) as conn:
            row = conn.execute(
                "SELECT consumed_state FROM invocation_authorizations "
                "WHERE authorization_id=?",
                (auth.invocation_authorization_id,),
            ).fetchone()
        assert row == ("CONSUMED",)
        assert current.claim_and_fence(
            lease.attempt_id, resolution, auth,
        ).status == "UNKNOWN"
    finally:
        start.close()


def test_post_fence_commit_failure_is_sticky_unknown(tmp_path):
    agent = "opencode-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        auth = current.issue(lease.attempt_id, resolution).authorization

        def fail_after_commit():
            raise RuntimeError("injected post-fence-commit failure")

        current.fence_store._after_claim_commit = fail_after_commit
        first = current.claim_and_fence(lease.attempt_id, resolution, auth)
        assert first.status == "UNKNOWN"
        persisted = current.fence_store.get(lease.attempt_id)
        assert persisted is not None
        assert auth_store.consumed_count() == 1

        reopened_auth = DurableInvocationAuthorizationStore(
            auth_store.path, anchor_path=auth_store.anchor_path,
        )
        reopened = owner(authority, start, reopened_auth)
        assert reopened.claim_and_fence(
            lease.attempt_id, resolution, auth,
        ).status == "UNKNOWN"
        assert reopened.fence_store.get(lease.attempt_id) == persisted
        assert reopened_auth.consumed_count() == 1
    finally:
        start.close()


def test_pre_fence_commit_failure_is_sticky_unknown(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        auth_store = qualification_store(tmp_path)
        current = owner(authority, start, auth_store)
        resolution = fake_resolution(agent)
        current.bridge_store.reserve(lease.attempt_id, resolution)
        auth = current.issue(lease.attempt_id, resolution).authorization

        def fail_before_commit(_):
            raise RuntimeError("injected pre-fence-commit failure")

        current.fence_store._before_claim_commit = fail_before_commit
        assert current.claim_and_fence(
            lease.attempt_id, resolution, auth,
        ).status == "UNKNOWN"
        assert current.fence_store.get(lease.attempt_id) is None
        assert auth_store.consumed_count() == 1

        reopened_auth = DurableInvocationAuthorizationStore(
            auth_store.path, anchor_path=auth_store.anchor_path,
        )
        reopened = owner(authority, start, reopened_auth)
        assert reopened.claim_and_fence(
            lease.attempt_id, resolution, auth,
        ).status == "UNKNOWN"
        assert reopened.fence_store.get(lease.attempt_id) is None
        assert reopened_auth.consumed_count() == 1
    finally:
        start.close()
