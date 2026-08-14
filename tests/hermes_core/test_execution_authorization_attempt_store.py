"""Focused EA-4B.2 persistence tests for ExecutionAttempt.

Proves schema v5, execution_attempts table, read/write APIs,
integrity validation, tamper detection, ATTEMPT_RECORDED ledger event,
and schema compatibility.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from tools.hermes_core.execution_authorization import (
    ExecutionAttempt,
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
    build_execution_attempt,
    build_execution_claim,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.execution_authorization_store import (
    ExecutionAuthorizationIntegrityError,
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


def make_attempt(**overrides) -> ExecutionAttempt:
    defaults = dict(
        authorization_id="execution-authorization-" + "a" * 16,
        authorization_hash="a" * 64,
        request_id="execution-authorization-request-" + "b" * 16,
        request_hash="b" * 64,
        decision_id="execution-authorization-decision-" + "c" * 16,
        decision_hash="c" * 64,
        claim_id="execution-authorization-claim-" + "d" * 16,
        claim_hash="d" * 64,
        task_id="task-1",
        attempt_number=1,
        attempt_actor=ExecutionAttemptActor(
            actor_id="runtime-orchestrator",
            actor_type="SYSTEM",
            actor_context="node-1",
        ),
        attempt_requested_at="2026-08-12T21:30:00Z",
        attempt_recorded_at="2026-08-12T21:30:01Z",
        claim_expires_at="2026-08-12T22:00:00Z",
        must_start_by="2026-08-12T21:35:00Z",
        input_hash="e" * 64,
        operation="run-sandboxed",
        worker_class="restricted-sandbox",
        status=ExecutionAttemptStatus.RECORDED,
    )
    defaults.update(overrides)
    return build_execution_attempt(**defaults)


def setup_authorization_and_claim(store, task_id="task-1"):
    """Helper to set up a valid Authorization and Claim lineage."""
    policy = _make_policy()
    actor = _make_actor()
    scope = _make_scope()

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

    # Build the decision first (derives decision_id/decision_hash)
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

    # Align the decision's authorization_id to the derived authorization id
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


class TestSchemaV5(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)

    def tearDown(self):
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def test_fresh_v5_opens(self):
        store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.assertTrue(store.verify_integrity().ok)
        store.close()

    def test_v4_fails_closed(self):
        import sqlite3
        conn = sqlite3.connect(self.ea_db)
        conn.execute("CREATE TABLE authority_schema_version (version INTEGER)")
        conn.execute("INSERT INTO authority_schema_version (version) VALUES (4)")
        conn.commit()
        conn.close()
        with self.assertRaises(Exception):
            SQLiteExecutionAuthorizationStore(self.ea_db)

    def test_v3_fails_closed(self):
        import sqlite3
        conn = sqlite3.connect(self.ea_db)
        conn.execute("CREATE TABLE authority_schema_version (version INTEGER)")
        conn.execute("INSERT INTO authority_schema_version (version) VALUES (3)")
        conn.commit()
        conn.close()
        with self.assertRaises(Exception):
            SQLiteExecutionAuthorizationStore(self.ea_db)

    def test_v2_fails_closed(self):
        import sqlite3
        conn = sqlite3.connect(self.ea_db)
        conn.execute("CREATE TABLE authority_schema_version (version INTEGER)")
        conn.execute("INSERT INTO authority_schema_version (version) VALUES (2)")
        conn.commit()
        conn.close()
        with self.assertRaises(Exception):
            SQLiteExecutionAuthorizationStore(self.ea_db)

    def test_v1_fails_closed(self):
        import sqlite3
        conn = sqlite3.connect(self.ea_db)
        conn.execute("CREATE TABLE authority_schema_version (version INTEGER)")
        conn.execute("INSERT INTO authority_schema_version (version) VALUES (1)")
        conn.commit()
        conn.close()
        with self.assertRaises(Exception):
            SQLiteExecutionAuthorizationStore(self.ea_db)

    def test_future_schema_fails_closed(self):
        import sqlite3
        conn = sqlite3.connect(self.ea_db)
        conn.execute("CREATE TABLE authority_schema_version (version INTEGER)")
        conn.execute("INSERT INTO authority_schema_version (version) VALUES (99)")
        conn.commit()
        conn.close()
        with self.assertRaises(Exception):
            SQLiteExecutionAuthorizationStore(self.ea_db)


class TestAttemptPersistence(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_authorization_and_claim(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def _make_attempt(self, **overrides):
        defaults = dict(
            authorization_id=self.auth.authorization_id,
            authorization_hash=self.auth.artifact_hash,
            request_id=self.auth.request_id,
            request_hash=self.auth.request_hash,
            decision_id=self.auth.decision_id,
            decision_hash=self.auth.decision_hash,
            claim_id=self.claim.claim_id,
            claim_hash=self.claim.artifact_hash,
            task_id=self.auth.task_id,
        )
        defaults.update(overrides)
        return make_attempt(**defaults)

    def test_insert_and_read(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        loaded = self.store.get_attempt(attempt.attempt_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.attempt_id, attempt.attempt_id)
        self.assertEqual(loaded.authorization_id, attempt.authorization_id)
        self.assertEqual(loaded.claim_id, attempt.claim_id)
        self.assertEqual(loaded.task_id, attempt.task_id)
        self.assertEqual(loaded.attempt_number, attempt.attempt_number)
        self.assertEqual(loaded.attempt_actor_id, attempt.attempt_actor_id)
        self.assertEqual(loaded.attempt_actor_type, attempt.attempt_actor_type)
        self.assertEqual(loaded.attempt_actor_context, attempt.attempt_actor_context)
        self.assertEqual(loaded.operation, attempt.operation)
        self.assertEqual(loaded.worker_class, attempt.worker_class)
        self.assertEqual(loaded.input_hash, attempt.input_hash)
        self.assertEqual(loaded.must_start_by, attempt.must_start_by)
        self.assertEqual(loaded.status, attempt.status)
        self.assertEqual(loaded.artifact_hash, attempt.artifact_hash)
        self.assertTrue(loaded.verify_hash())

    def test_artifact_hash_preserved(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        loaded = self.store.get_attempt(attempt.attempt_id)
        self.assertEqual(loaded.artifact_hash, attempt.artifact_hash)

    def test_get_attempts_for_authorization(self):
        a1 = self._make_attempt(attempt_number=1)
        a2 = self._make_attempt(attempt_number=2)
        self.store.record_attempt(a1)
        self.store.record_attempt(a2)
        attempts = self.store.get_attempts_for_authorization(a1.authorization_id)
        self.assertEqual(len(attempts), 2)

    def test_get_attempt_for_claim(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        loaded = self.store.get_attempt_for_claim(attempt.claim_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.attempt_id, attempt.attempt_id)

    def test_get_attempt_returns_none_for_missing(self):
        loaded = self.store.get_attempt("nonexistent")
        self.assertIsNone(loaded)

    def test_multiple_attempt_numbers_structurally_possible(self):
        a1 = self._make_attempt(attempt_number=1)
        a2 = self._make_attempt(attempt_number=2)
        self.store.record_attempt(a1)
        self.store.record_attempt(a2)
        attempts = self.store.get_attempts_for_authorization(a1.authorization_id)
        numbers = sorted(a.attempt_number for a in attempts)
        self.assertEqual(numbers, [1, 2])

    def test_duplicate_attempt_number_rejected(self):
        a1 = self._make_attempt(attempt_number=1)
        a2 = self._make_attempt(attempt_number=1)
        self.store.record_attempt(a1)
        with self.assertRaises(Exception):
            self.store.record_attempt(a2)

    def test_attempt_recorded_once(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        events = [e for e in self.store.get_authority_events()
                  if e.event_type == "ATTEMPT_RECORDED"]
        self.assertEqual(len(events), 1)


class TestTamperDetection(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_authorization_and_claim(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def _tamper_column(self, column: str, value):
        import sqlite3
        conn = sqlite3.connect(self.ea_db)
        conn.execute(
            f"UPDATE execution_attempts SET {column} = ? WHERE artifact_id IN "
            f"(SELECT artifact_id FROM execution_attempts LIMIT 1)",
            (value,)
        )
        conn.commit()
        conn.close()

    def _make_attempt(self, **overrides):
        defaults = dict(
            authorization_id=self.auth.authorization_id,
            authorization_hash=self.auth.artifact_hash,
            request_id=self.auth.request_id,
            request_hash=self.auth.request_hash,
            decision_id=self.auth.decision_id,
            decision_hash=self.auth.decision_hash,
            claim_id=self.claim.claim_id,
            claim_hash=self.claim.artifact_hash,
            task_id=self.auth.task_id,
        )
        defaults.update(overrides)
        return make_attempt(**defaults)

    def test_authorization_id_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("authorization_id", "tampered-id")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_authorization_hash_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("authorization_hash", "f" * 64)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_request_id_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("request_id", "tampered-request")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_request_hash_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("request_hash", "f" * 64)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_decision_id_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("decision_id", "tampered-decision")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_decision_hash_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("decision_hash", "f" * 64)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_claim_id_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("claim_id", "tampered-claim")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_claim_hash_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("claim_hash", "f" * 64)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_task_id_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("task_id", "tampered-task")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_attempt_number_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("attempt_number", 99)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_attempt_actor_id_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("attempt_actor_id", "tampered-actor")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_attempt_actor_type_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("attempt_actor_type", "tampered-type")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_attempt_actor_context_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("attempt_actor_context", "tampered-context")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_attempt_requested_at_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("attempt_requested_at", "2027-01-01T00:00:00Z")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_attempt_recorded_at_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("attempt_recorded_at", "2027-01-01T00:00:00Z")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_claim_expires_at_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("claim_expires_at", "2027-01-01T00:00:00Z")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_must_start_by_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("must_start_by", "2027-01-01T00:00:00Z")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_input_hash_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("input_hash", "f" * 64)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_operation_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("operation", "tampered-op")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_worker_class_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("worker_class", "tampered-worker")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_status_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("status", "EXECUTING")
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)

    def test_artifact_hash_tamper_fails(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        self._tamper_column("artifact_hash", "f" * 64)
        with self.assertRaises(ExecutionAuthorizationIntegrityError):
            self.store.get_attempt(attempt.attempt_id)


class TestOrphanLineageRejection(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_authorization_and_claim(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def _make_attempt(self, **overrides):
        defaults = dict(
            authorization_id=self.auth.authorization_id,
            authorization_hash=self.auth.artifact_hash,
            request_id=self.auth.request_id,
            request_hash=self.auth.request_hash,
            decision_id=self.auth.decision_id,
            decision_hash=self.auth.decision_hash,
            claim_id=self.claim.claim_id,
            claim_hash=self.claim.artifact_hash,
            task_id=self.auth.task_id,
        )
        defaults.update(overrides)
        return make_attempt(**defaults)

    def test_missing_authorization_rejects(self):
        # Use a completely non-existent authorization_id AND claim_id
        attempt = make_attempt(
            authorization_id="execution-authorization-" + "f" * 16,
            authorization_hash="f" * 64,
            request_id=self.auth.request_id,
            request_hash=self.auth.request_hash,
            decision_id=self.auth.decision_id,
            decision_hash=self.auth.decision_hash,
            claim_id="execution-authorization-claim-" + "f" * 16,
            claim_hash="f" * 64,
            task_id=self.auth.task_id,
        )
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)
        # Verify zero residue
        events = [e for e in self.store.get_authority_events()
                  if e.event_type == "ATTEMPT_RECORDED"]
        self.assertEqual(len(events), 0)

    def test_missing_claim_rejects(self):
        # Use a non-existent claim_id but valid authorization_id
        attempt = self._make_attempt(
            claim_id="execution-authorization-claim-" + "f" * 16,
            claim_hash="f" * 64,
        )
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)
        events = [e for e in self.store.get_authority_events()
                  if e.event_type == "ATTEMPT_RECORDED"]
        self.assertEqual(len(events), 0)

    def test_claim_from_different_authorization_rejects(self):
        # Set up a second authorization + claim with a different task_id
        auth2, claim2 = setup_authorization_and_claim(
            self.store, task_id="task-2"
        )
        # Attempt references auth1's authorization_id but claim2's claim_id
        # The lookup will find claim2 by claim_id, but its authorization_id
        # won't match the attempt's authorization_id
        attempt = self._make_attempt(
            claim_id=claim2.claim_id,
            claim_hash=claim2.artifact_hash,
        )
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)
        events = [e for e in self.store.get_authority_events()
                  if e.event_type == "ATTEMPT_RECORDED"]
        self.assertEqual(len(events), 0)

    def test_authorization_hash_mismatch_rejects(self):
        attempt = self._make_attempt(authorization_hash="f" * 64)
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)

    def test_request_id_mismatch_rejects(self):
        attempt = self._make_attempt(
            request_id="execution-authorization-request-" + "f" * 16
        )
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)

    def test_request_hash_mismatch_rejects(self):
        attempt = self._make_attempt(request_hash="f" * 64)
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)

    def test_decision_id_mismatch_rejects(self):
        attempt = self._make_attempt(
            decision_id="execution-authorization-decision-" + "f" * 16
        )
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)

    def test_decision_hash_mismatch_rejects(self):
        attempt = self._make_attempt(decision_hash="f" * 64)
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)

    def test_claim_hash_mismatch_rejects(self):
        attempt = self._make_attempt(claim_hash="f" * 64)
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)

    def test_task_id_mismatch_rejects(self):
        attempt = self._make_attempt(task_id="different-task")
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)

    def test_failure_leaves_zero_attempt_rows(self):
        attempt = self._make_attempt(authorization_hash="f" * 64)
        with self.assertRaises(Exception):
            self.store.record_attempt(attempt)
        # Verify no attempt rows exist for this authorization
        attempts = self.store.get_attempts_for_authorization(self.auth.authorization_id)
        self.assertEqual(len(attempts), 0)


class TestCapabilityBoundary(unittest.TestCase):
    def setUp(self):
        self.ea_tmp = tempfile.mkdtemp()
        self.ea_db = os.path.join(self.ea_tmp, "ea.db")
        set_execution_authority_db_path_override(self.ea_db)
        self.store = SQLiteExecutionAuthorizationStore(self.ea_db)
        self.auth, self.claim = setup_authorization_and_claim(self.store)

    def tearDown(self):
        self.store.close()
        close_execution_authorization_store()
        reset_execution_authorization_store_cache()

    def _make_attempt(self, **overrides):
        defaults = dict(
            authorization_id=self.auth.authorization_id,
            authorization_hash=self.auth.artifact_hash,
            request_id=self.auth.request_id,
            request_hash=self.auth.request_hash,
            decision_id=self.auth.decision_id,
            decision_hash=self.auth.decision_hash,
            claim_id=self.claim.claim_id,
            claim_hash=self.claim.artifact_hash,
            task_id=self.auth.task_id,
        )
        defaults.update(overrides)
        return make_attempt(**defaults)

    def test_no_execution_transition(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        loaded = self.store.get_attempt(attempt.attempt_id)
        self.assertEqual(loaded.status, ExecutionAttemptStatus.RECORDED)
        self.assertNotEqual(loaded.status, "EXECUTING")

    def test_status_is_recorded(self):
        attempt = self._make_attempt()
        self.store.record_attempt(attempt)
        loaded = self.store.get_attempt(attempt.attempt_id)
        self.assertEqual(loaded.status.value, "RECORDED")


if __name__ == "__main__":
    unittest.main()
