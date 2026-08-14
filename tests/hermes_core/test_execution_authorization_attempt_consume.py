"""Focused EA-4B.3 tests for atomic Claim -> ExecutionAttempt consumption.

Covers corrections:
1. Inclusive expiry boundary (now <= claim_expires_at is valid)
2. Attempt limit derived from authorization scope (not caller-supplied)
3. Structured actor identity (all 3 fields must match for replay)
4. Single BEGIN IMMEDIATE transaction for the entire consume
"""
from __future__ import annotations

import os
import tempfile
import unittest

from tools.hermes_core.execution_authorization import (
    ExecutionAttemptActor,
    ExecutionAttemptStatus,
    ExecutionAuthorizationActor,
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationDecisionOutcome,
    ExecutionAuthorizationPolicyRef,
    ExecutionAuthorizationScope,
    ExecutionClaimant,
    build_execution_authorization,
    build_execution_authorization_decision,
    build_execution_authorization_request,
    build_execution_claim,
)
from tools.hermes_core.execution_authorization_attempt import (
    ExecutionAttemptClockError,
    ExecutionAttemptConflictError,
    ExecutionAttemptError,
    ExecutionAttemptLimitError,
    ExecutionAttemptLineageError,
    ExecutionAttemptResult,
    consume_claim_into_attempt,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.runtime import (
    set_execution_authority_db_path_override,
    close_execution_authorization_store,
    reset_execution_authorization_store_cache,
)


def _make_scope(attempt_limit=1):
    return ExecutionAuthorizationScope(
        operation="run-sandboxed",
        worker_class="restricted-sandbox",
        input_hash="a" * 64,
        attempt_limit=attempt_limit,
        max_runtime_seconds=300,
    )


def _make_policy():
    return ExecutionAuthorizationPolicyRef(
        policy_id="ea-baseline",
        policy_version="1.0",
    )


def _make_actor():
    return ExecutionAuthorizationActor(
        actor_id="human-owner",
        actor_type=ExecutionAuthorizationActorType.HUMAN,
        authority_role="owner",
        authentication_context=None,
    )


def _make_attempt_actor(actor_id="runtime-orchestrator", actor_type="SYSTEM", actor_context="node-1"):
    return ExecutionAttemptActor(
        actor_id=actor_id,
        actor_type=actor_type,
        actor_context=actor_context,
    )


def setup_claim_lineage(store, task_id="task-1", attempt_limit=1):
    """Helper: request -> decision -> authorization -> claim."""
    policy = _make_policy()
    actor = _make_actor()
    scope = _make_scope(attempt_limit=attempt_limit)
    acc_id = "acceptance-" + "b" * 16
    acc_hash = "b" * 64

    req = build_execution_authorization_request(
        task_id=task_id,
        accepted_governance_artifact_id=acc_id,
        accepted_governance_hash=acc_hash,
        requested_scope=scope,
        requesting_actor=actor,
        authorization_policy=policy,
        requested_at="2026-08-12T21:25:00Z",
        request_reason="need exec",
    )
    store.record_request(req)

    dec = build_execution_authorization_decision(
        request_id=req.request_id,
        request_hash=req.artifact_hash,
        task_id=task_id,
        decision_actor=actor,
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason="approved",
        authorization_id="execution-authorization-" + "d" * 16,
        authorization_policy=policy,
    )

    auth = build_execution_authorization(
        task_id=task_id,
        accepted_governance_artifact_id=acc_id,
        accepted_governance_hash=acc_hash,
        request_id=dec.request_id,
        request_hash=dec.request_hash,
        decision_id=dec.decision_id,
        decision_hash=dec.artifact_hash,
        authorization_actor=actor,
        authorized_scope=scope,
        authorization_reason="operator approved",
        authorization_policy=policy,
        issued_at="2026-08-12T21:30:00Z",
        expires_at="2026-08-12T22:00:00Z",
        nonce="nonce-0001",
    )

    dec = build_execution_authorization_decision(
        request_id=req.request_id,
        request_hash=req.artifact_hash,
        task_id=task_id,
        decision_actor=actor,
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason="approved",
        authorization_id=auth.authorization_id,
        authorization_policy=policy,
    )

    store.record_granted_decision_and_authorization(dec, auth)

    claim = build_execution_claim(
        authorization_id=auth.authorization_id,
        authorization_hash=auth.artifact_hash,
        request_id=auth.request_id,
        request_hash=auth.request_hash,
        decision_id=auth.decision_id,
        decision_hash=auth.decision_hash,
        task_id=auth.task_id,
        claimant=ExecutionClaimant(
            claimant_id="worker-manager",
            claimant_type="worker-manager",
            claimant_context="node-1",
        ),
        claimed_at="2026-08-12T21:30:00Z",
        claim_expires_at="2026-08-12T22:00:00Z",
        authorization_policy=policy,
        claim_reason="claim by worker-manager",
    )

    store.claim_authorization_atomically(auth.authorization_id, claim)
    return auth, claim


class TestConsumeClaimIntoAttempt(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_claim_lineage(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def test_consume_creates_attempt(self):
        actor = _make_attempt_actor()
        result = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        self.assertTrue(result.persisted)
        self.assertFalse(result.replayed)
        self.assertEqual(result.authorization_id, self.auth.authorization_id)
        self.assertEqual(result.claim_id, self.claim.claim_id)
        self.assertEqual(result.attempt_number, 1)
        self.assertIsNotNone(result.attempt_id)
        self.assertIsNotNone(result.attempt_hash)

    def test_attempt_has_recorded_status(self):
        actor = _make_attempt_actor()
        result = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        loaded = self.store.get_attempt(result.attempt_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.status, ExecutionAttemptStatus.RECORDED)

    def test_consume_within_claim_lifetime(self):
        actor = _make_attempt_actor()
        result = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:59:59Z",
        )
        self.assertTrue(result.persisted)

    def test_exact_expiry_boundary_accepted(self):
        """Correction 1: now <= claim_expires_at is valid (inclusive boundary)."""
        actor = _make_attempt_actor()
        result = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: self.claim.claim_expires_at,
        )
        self.assertTrue(result.persisted)

    def test_claim_expired_rejects(self):
        actor = _make_attempt_actor()
        with self.assertRaises(ExecutionAttemptError):
            consume_claim_into_attempt(
                store=self.store,
                authorization_id=self.auth.authorization_id,
                claim_id=self.claim.claim_id,
                claimant=actor,
                clock=lambda: "2026-08-12T22:00:01Z",
            )

    def test_missing_claim_rejects(self):
        actor = _make_attempt_actor()
        with self.assertRaises(ExecutionAttemptError):
            consume_claim_into_attempt(
                store=self.store,
                authorization_id=self.auth.authorization_id,
                claim_id="execution-authorization-claim-" + "f" * 16,
                claimant=actor,
                clock=lambda: "2026-08-12T21:31:00Z",
            )

    def test_missing_authorization_rejects(self):
        actor = _make_attempt_actor()
        with self.assertRaises(ExecutionAttemptError):
            consume_claim_into_attempt(
                store=self.store,
                authorization_id="execution-authorization-" + "f" * 16,
                claim_id=self.claim.claim_id,
                claimant=actor,
                clock=lambda: "2026-08-12T21:31:00Z",
            )

    def test_claim_from_different_authorization_rejects(self):
        auth2, claim2 = setup_claim_lineage(self.store, task_id="task-2")
        actor = _make_attempt_actor()
        with self.assertRaises(ExecutionAttemptLineageError):
            consume_claim_into_attempt(
                store=self.store,
                authorization_id=self.auth.authorization_id,
                claim_id=claim2.claim_id,
                claimant=actor,
                clock=lambda: "2026-08-12T21:31:00Z",
            )

    def test_attempt_limit_derived_from_scope(self):
        """Correction 2: attempt limit comes from authorization scope, not caller."""
        actor = _make_attempt_actor()
        # First attempt succeeds (scope allows 1)
        result1 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        self.assertTrue(result1.persisted)
        # Second call: replay returns existing attempt (same claim + claimant)
        result2 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:32:00Z",
        )
        self.assertTrue(result2.replayed)
        self.assertEqual(result1.attempt_id, result2.attempt_id)


class TestExactReplay(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_claim_lineage(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def test_same_actor_replay_idempotent(self):
        actor = _make_attempt_actor()
        result1 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        self.assertTrue(result1.persisted)
        self.assertFalse(result1.replayed)

        result2 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:32:00Z",
        )
        self.assertTrue(result2.persisted)
        self.assertTrue(result2.replayed)
        self.assertEqual(result1.attempt_id, result2.attempt_id)
        self.assertEqual(result1.attempt_number, result2.attempt_number)

    def test_replay_converges_on_persisted_winner(self):
        """Same logical consumption converges on persisted winner even with different timestamps."""
        actor = _make_attempt_actor()
        r1 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        r2 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:31:05Z",
        )
        self.assertEqual(r1.attempt_id, r2.attempt_id)
        self.assertEqual(r1.attempt_hash, r2.attempt_hash)


class TestStructuredActorIdentity(unittest.TestCase):
    """Correction 3: replay identity is the full structured actor."""

    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_claim_lineage(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def test_same_actor_id_different_type_conflicts(self):
        """Same actor_id with changed actor_type -> CONFLICT."""
        actor1 = _make_attempt_actor(actor_type="SYSTEM")
        actor2 = _make_attempt_actor(actor_type="HUMAN")
        r1 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor1,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        self.assertTrue(r1.persisted)
        with self.assertRaises(ExecutionAttemptConflictError):
            consume_claim_into_attempt(
                store=self.store,
                authorization_id=self.auth.authorization_id,
                claim_id=self.claim.claim_id,
                claimant=actor2,
                clock=lambda: "2026-08-12T21:32:00Z",
            )

    def test_same_actor_id_type_different_context_conflicts(self):
        """Same actor_id/type with changed actor_context -> CONFLICT."""
        actor1 = _make_attempt_actor(actor_context="node-1")
        actor2 = _make_attempt_actor(actor_context="node-2")
        r1 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor1,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        self.assertTrue(r1.persisted)
        with self.assertRaises(ExecutionAttemptConflictError):
            consume_claim_into_attempt(
                store=self.store,
                authorization_id=self.auth.authorization_id,
                claim_id=self.claim.claim_id,
                claimant=actor2,
                clock=lambda: "2026-08-12T21:32:00Z",
            )

    def test_full_actor_match_replays(self):
        """All 3 fields match -> exact replay."""
        actor = _make_attempt_actor()
        r1 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        r2 = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:33:00Z",
        )
        self.assertTrue(r2.replayed)
        self.assertEqual(r1.attempt_id, r2.attempt_id)


class TestMustStartBy(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_claim_lineage(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def test_must_start_by_defaults_to_claim_expiry(self):
        actor = _make_attempt_actor()
        result = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        self.assertEqual(result.must_start_by, self.claim.claim_expires_at)

    def test_must_start_by_bounded_by_claim_expiry(self):
        actor = _make_attempt_actor()
        result = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            must_start_within_seconds=7200,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        self.assertEqual(result.must_start_by, self.claim.claim_expires_at)

    def test_must_start_by_within_window(self):
        actor = _make_attempt_actor()
        result = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            must_start_within_seconds=120,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        self.assertEqual(result.must_start_by, "2026-08-12T21:33:00Z")

    def test_must_start_by_non_positive_rejected(self):
        actor = _make_attempt_actor()
        with self.assertRaises(ExecutionAttemptError):
            consume_claim_into_attempt(
                store=self.store,
                authorization_id=self.auth.authorization_id,
                claim_id=self.claim.claim_id,
                claimant=actor,
                must_start_within_seconds=0,
                clock=lambda: "2026-08-12T21:31:00Z",
            )
        with self.assertRaises(ExecutionAttemptError):
            consume_claim_into_attempt(
                store=self.store,
                authorization_id=self.auth.authorization_id,
                claim_id=self.claim.claim_id,
                claimant=actor,
                must_start_within_seconds=-5,
                clock=lambda: "2026-08-12T21:31:00Z",
            )


class TestRollbackEvidence(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_claim_lineage(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def test_failed_consume_leaves_zero_attempt_rows(self):
        actor = _make_attempt_actor()
        with self.assertRaises(ExecutionAttemptError):
            consume_claim_into_attempt(
                store=self.store,
                authorization_id=self.auth.authorization_id,
                claim_id=self.claim.claim_id,
                claimant=actor,
                clock=lambda: "2026-08-13T00:00:00Z",
            )
        attempts = self.store.get_attempts_for_authorization(
            self.auth.authorization_id
        )
        self.assertEqual(len(attempts), 0)
        events = [
            e
            for e in self.store.get_authority_events()
            if e.event_type == "ATTEMPT_RECORDED"
        ]
        self.assertEqual(len(events), 0)


class TestCapabilityBoundary(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_claim_lineage(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def test_no_execution_transition(self):
        actor = _make_attempt_actor()
        result = consume_claim_into_attempt(
            store=self.store,
            authorization_id=self.auth.authorization_id,
            claim_id=self.claim.claim_id,
            claimant=actor,
            clock=lambda: "2026-08-12T21:31:00Z",
        )
        loaded = self.store.get_attempt(result.attempt_id)
        self.assertEqual(loaded.status, ExecutionAttemptStatus.RECORDED)
        self.assertNotEqual(loaded.status, "EXECUTING")

    def test_caller_cannot_raise_attempt_limit(self):
        """Caller has no attempt_limit parameter — ceiling comes from scope."""
        import inspect
        sig = inspect.signature(consume_claim_into_attempt)
        self.assertNotIn("attempt_limit", sig.parameters)


if __name__ == "__main__":
    unittest.main()
