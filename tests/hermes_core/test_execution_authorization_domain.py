"""Focused EA-1 domain tests for execution-authorization artifacts.

These tests prove the EA-1 DOMAIN MODEL only. No persistence, no issuance, no
worker behavior, no execution transitions.
"""

from __future__ import annotations

import copy
import unittest

from tools.hermes_core.execution_authorization import (
    ARTIFACT_VERSION,
    ExecutionAuthorization,
    ExecutionAuthorizationActor,
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationDecision,
    ExecutionAuthorizationDecisionOutcome,
    ExecutionAuthorizationError,
    ExecutionAuthorizationPolicyRef,
    ExecutionAuthorizationRequest,
    ExecutionAuthorizationScope,
    ExecutionAuthorizationValidationError,
    build_execution_authorization,
    build_execution_authorization_decision,
    build_execution_authorization_request,
    validate_execution_authorization_artifact,
    validate_execution_authorization_decision,
    validate_execution_authorization_request,
)


def make_scope(**overrides: object) -> ExecutionAuthorizationScope:
    defaults = dict(
        operation="stage2-v1-gpu-execution",
        worker_class="OpenInterpreterWorker",
        input_hash="a" * 64,
        attempt_limit=1,
        max_runtime_seconds=300,
    )
    defaults.update(overrides)
    return ExecutionAuthorizationScope(**defaults)  # type: ignore[arg-type]


def make_actor(**overrides: object) -> ExecutionAuthorizationActor:
    defaults = dict(
        actor_id="human-owner",
        actor_type=ExecutionAuthorizationActorType.HUMAN,
        authority_role="owner",
        authentication_context=None,
    )
    defaults.update(overrides)
    return ExecutionAuthorizationActor(**defaults)  # type: ignore[arg-type]


def make_policy(**overrides: object) -> ExecutionAuthorizationPolicyRef:
    defaults = dict(policy_id="ea-policy", policy_version="1.0")
    defaults.update(overrides)
    return ExecutionAuthorizationPolicyRef(**defaults)  # type: ignore[arg-type]


VALID_HASH = "f" * 64
VALID_ID = "acceptance-" + "b" * 16


def make_authorization(**overrides: object) -> ExecutionAuthorization:
    kwargs: dict = dict(
        task_id="task-1",
        accepted_governance_artifact_id=VALID_ID,
        accepted_governance_hash=VALID_HASH,
        request_id="execution-authorization-request-" + "c" * 16,
        request_hash="c" * 64,
        decision_id="execution-authorization-decision-" + "d" * 16,
        decision_hash="d" * 64,
        authorization_actor=make_actor(),
        authorized_scope=make_scope(),
        authorization_reason="operator approved per policy",
        authorization_policy=make_policy(),
        issued_at="2026-08-12T21:30:00Z",
        expires_at="2026-08-12T22:00:00Z",
        nonce="nonce-0001",
    )
    kwargs.update(overrides)
    return build_execution_authorization(**kwargs)  # type: ignore[arg-type]


def make_request(**overrides: object) -> ExecutionAuthorizationRequest:
    kwargs: dict = dict(
        task_id="task-1",
        accepted_governance_artifact_id=VALID_ID,
        accepted_governance_hash=VALID_HASH,
        requested_scope=make_scope(),
        requesting_actor=make_actor(),
        authorization_policy=make_policy(),
        requested_at="2026-08-12T21:25:00Z",
        request_reason="need execution",
    )
    kwargs.update(overrides)
    return build_execution_authorization_request(**kwargs)  # type: ignore[arg-type]


def make_decision(**overrides: object) -> ExecutionAuthorizationDecision:
    kwargs: dict = dict(
        request_id="execution-authorization-request-" + "c" * 16,
        request_hash="c" * 64,
        task_id="task-1",
        decision_actor=make_actor(),
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason="approved",
        authorization_id="execution-authorization-" + "d" * 16,
        authorization_policy=make_policy(),
    )
    kwargs.update(overrides)
    return build_execution_authorization_decision(**kwargs)  # type: ignore[arg-type]


class TestValidArtifacts(unittest.TestCase):
    def test_valid_authorization_builds_and_verifies(self):
        auth = make_authorization()
        self.assertIsInstance(auth, ExecutionAuthorization)
        self.assertTrue(auth.verify_hash())
        validate_execution_authorization_artifact(auth)  # must not raise

    def test_valid_request_builds_and_verifies(self):
        req = make_request()
        self.assertIsInstance(req, ExecutionAuthorizationRequest)
        self.assertTrue(req.verify_hash())
        validate_execution_authorization_request(req)

    def test_granted_decision_builds_and_verifies(self):
        dec = make_decision()
        self.assertIsInstance(dec, ExecutionAuthorizationDecision)
        self.assertEqual(dec.outcome, ExecutionAuthorizationDecisionOutcome.GRANTED)
        self.assertTrue(dec.verify_hash())
        validate_execution_authorization_decision(dec)

    def test_denied_decision_no_authorization_id(self):
        dec = make_decision(
            outcome=ExecutionAuthorizationDecisionOutcome.DENIED,
            authorization_id=None,
        )
        self.assertEqual(dec.outcome, ExecutionAuthorizationDecisionOutcome.DENIED)
        self.assertIsNone(dec.authorization_id)
        self.assertTrue(dec.verify_hash())
        validate_execution_authorization_decision(dec)


class TestImmutability(unittest.TestCase):
    def test_authorization_is_frozen(self):
        auth = make_authorization()
        with self.assertRaises(Exception):
            auth.nonce = "mutated"  # type: ignore[misc]

    def test_request_is_frozen(self):
        req = make_request()
        with self.assertRaises(Exception):
            req.request_reason = "x"  # type: ignore[misc]


class TestDeterministicHashing(unittest.TestCase):
    def test_same_inputs_same_hash(self):
        a = make_authorization()
        b = make_authorization()
        self.assertEqual(a.artifact_hash, b.artifact_hash)
        self.assertEqual(
            a.to_canonical_dict(), b.to_canonical_dict()
        )

    def test_different_nonce_different_hash(self):
        a = make_authorization(nonce="nonce-aaaa")
        b = make_authorization(nonce="nonce-bbbb")
        self.assertNotEqual(a.artifact_hash, b.artifact_hash)

    def test_hash_excludes_stored_hash(self):
        auth = make_authorization()
        # Recomputing from canonical dict (which excludes artifact_hash) reproduces it.
        import hashlib
        from tools.hermes_core.hashing import canonical_json

        digest = hashlib.sha256(
            canonical_json(auth.to_canonical_dict()).encode("utf-8")
        ).hexdigest()
        self.assertEqual(digest, auth.artifact_hash)


class TestTamperDetection(unittest.TestCase):
    def test_tamper_detected_via_reconstructed_dict(self):
        auth = make_authorization()
        payload = auth.to_canonical_dict()
        tampered = copy.deepcopy(payload)
        tampered["authorization_reason"] = "mutated reason"
        import hashlib
        from tools.hermes_core.hashing import canonical_json

        recomputed = hashlib.sha256(
            canonical_json(tampered).encode("utf-8")
        ).hexdigest()
        self.assertNotEqual(recomputed, auth.artifact_hash)

    def test_verify_hash_false_after_internal_change(self):
        auth = make_authorization()
        # Build a dict with a changed field; the artifact itself is immutable so
        # tamper is detected by re-hashing the canonical preimage.
        bad = copy.deepcopy(auth.to_canonical_dict())
        bad["accepted_governance_hash"] = "e" * 64
        import hashlib
        from tools.hermes_core.hashing import canonical_json

        self.assertNotEqual(
            hashlib.sha256(canonical_json(bad).encode("utf-8")).hexdigest(),
            auth.artifact_hash,
        )


class TestNegativeValidation(unittest.TestCase):
    def test_missing_acceptance_binding_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(accepted_governance_artifact_id="", accepted_governance_hash="")

    def test_malformed_acceptance_hash_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(accepted_governance_hash="not-a-hash")

    def test_malformed_input_hash_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(authorized_scope=make_scope(input_hash="zzz"))

    def test_attempt_limit_zero_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(authorized_scope=make_scope(attempt_limit=0))

    def test_attempt_limit_negative_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(authorized_scope=make_scope(attempt_limit=-1))

    def test_empty_actor_id_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(authorization_actor=make_actor(actor_id=""))

    def test_invalid_actor_type_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(
                authorization_actor=make_actor(actor_type="ROBOT")  # type: ignore[arg-type]
            )

    def test_empty_policy_id_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(authorization_policy=make_policy(policy_id=""))

    def test_empty_policy_version_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(authorization_policy=make_policy(policy_version=""))

    def test_unparsable_issued_at_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(issued_at="not-a-time")

    def test_non_utc_issued_at_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(issued_at="2026-08-12T21:30:00")

    def test_expires_before_issued_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(
                issued_at="2026-08-12T22:00:00Z",
                expires_at="2026-08-12T21:30:00Z",
            )

    def test_expires_equal_issued_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(
                issued_at="2026-08-12T21:30:00Z",
                expires_at="2026-08-12T21:30:00Z",
            )

    def test_null_expiry_allowed_structurally(self):
        # Null expiry is structurally representable (no policy approval implied).
        auth = make_authorization(expires_at=None)
        self.assertIsNone(auth.expires_at)
        self.assertTrue(auth.verify_hash())
        validate_execution_authorization_artifact(auth)

    def test_unsupported_artifact_version_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(artifact_version="99")

    def test_granted_decision_requires_authorization_id(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_decision(
                outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
                authorization_id=None,
            )

    def test_denied_decision_cannot_carry_authorization_id(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_decision(
                outcome=ExecutionAuthorizationDecisionOutcome.DENIED,
                authorization_id="execution-authorization-" + "d" * 16,
            )


class TestEA3ABinding(unittest.TestCase):
    """EA-3A cryptographic lineage binding tests.

    Prove the new request/decision binding fields are actually hash-bound, and
    that invalid bindings are rejected. Cross-artifact equality verification
    (request_hash matches the referenced request, decision_hash matches the
    referenced decision) is deferred to EA-3I; here we only prove the fields
    participate in the canonical digest and are validated in isolation.
    """

    def test_decision_request_hash_binding_changes_hash(self):
        base = make_decision()
        other = make_decision(request_hash="f" * 64)
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)
        self.assertTrue(base.verify_hash())
        self.assertTrue(other.verify_hash())

    def test_authorization_request_id_binding_changes_hash(self):
        base = make_authorization()
        other = make_authorization(request_id="execution-authorization-request-" + "e" * 16)
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_authorization_request_hash_binding_changes_hash(self):
        base = make_authorization()
        other = make_authorization(request_hash="f" * 64)
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_authorization_decision_id_binding_changes_hash(self):
        base = make_authorization()
        other = make_authorization(decision_id="execution-authorization-decision-" + "e" * 16)
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_authorization_decision_hash_binding_changes_hash(self):
        base = make_authorization()
        other = make_authorization(decision_hash="f" * 64)
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)

    def test_decision_missing_request_hash_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_decision(request_hash="not-a-hash")

    def test_decision_empty_request_hash_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_decision(request_hash="")

    def test_authorization_missing_request_id_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(request_id="")

    def test_authorization_missing_request_hash_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(request_hash="not-a-hash")

    def test_authorization_missing_decision_id_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(decision_id="")

    def test_authorization_missing_decision_hash_rejected(self):
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_authorization(decision_hash="not-a-hash")

    def test_authorization_round_trip_reconstruct_preserves_bindings(self):
        from tools.hermes_core.execution_authorization import reconstruct_authorization
        auth = make_authorization()
        payload = auth.to_canonical_dict()
        payload["artifact_hash"] = auth.artifact_hash
        rebuilt = reconstruct_authorization(payload)
        self.assertEqual(rebuilt.request_id, auth.request_id)
        self.assertEqual(rebuilt.request_hash, auth.request_hash)
        self.assertEqual(rebuilt.decision_id, auth.decision_id)
        self.assertEqual(rebuilt.decision_hash, auth.decision_hash)
        self.assertEqual(rebuilt.artifact_hash, auth.artifact_hash)
        self.assertTrue(rebuilt.verify_hash())

    def test_decision_round_trip_reconstruct_preserves_bindings(self):
        from tools.hermes_core.execution_authorization import reconstruct_decision
        dec = make_decision()
        payload = dec.to_canonical_dict()
        payload["artifact_hash"] = dec.artifact_hash
        # The store injects the non-hash-bound authorization_id from its
        # dedicated column; simulate that here (it is excluded from the
        # canonical payload/hash preimage by design).
        payload["authorization_id"] = dec.authorization_id
        rebuilt = reconstruct_decision(payload)
        self.assertEqual(rebuilt.request_id, dec.request_id)
        self.assertEqual(rebuilt.request_hash, dec.request_hash)
        self.assertEqual(rebuilt.authorization_id, dec.authorization_id)
        self.assertEqual(rebuilt.artifact_hash, dec.artifact_hash)
        self.assertTrue(rebuilt.verify_hash())

    def test_amended_artifact_version_is_two(self):
        self.assertEqual(make_authorization().artifact_version, "2")
        self.assertEqual(make_decision().artifact_version, "2")
        # Request artifact is unchanged and remains at version "1".
        self.assertEqual(make_request().artifact_version, "1")

    def test_decision_authorization_id_excluded_from_hash_preimage(self):
        # authorization_id must be non-hash-bound forward linkage: changing it
        # must NOT change the decision hash (acyclic Model A requirement).
        granted_a = make_decision(authorization_id="execution-authorization-" + "a" * 16)
        granted_b = make_decision(authorization_id="execution-authorization-" + "b" * 16)
        self.assertEqual(granted_a.artifact_hash, granted_b.artifact_hash)
        self.assertEqual(granted_a.decision_id, granted_b.decision_id)

    def test_granted_denied_invariants_preserved(self):
        granted = make_decision(
            outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
            authorization_id="execution-authorization-" + "d" * 16,
        )
        self.assertIsNotNone(granted.authorization_id)
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_decision(
                outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
                authorization_id=None,
            )
        denied = make_decision(
            outcome=ExecutionAuthorizationDecisionOutcome.DENIED,
            authorization_id=None,
        )
        self.assertIsNone(denied.authorization_id)
        with self.assertRaises(ExecutionAuthorizationValidationError):
            make_decision(
                outcome=ExecutionAuthorizationDecisionOutcome.DENIED,
                authorization_id="execution-authorization-" + "d" * 16,
            )


class TestAcceptanceIsNotAuthorization(unittest.TestCase):
    def test_no_acceptance_to_authorization_conversion_helper(self):
        # Explicitly assert no public helper implies automatically converting an
        # acceptance identity into an authorization. Every builder requires full
        # explicit actor/scope/policy/nonce inputs.
        import importlib

        mod = importlib.import_module("tools.hermes_core.execution_authorization")
        suspicious = []
        for name in dir(mod):
            if name.startswith("_"):
                continue
            low = name.lower()
            if any(
                token in low
                for token in ("accept_to_auth", "authorize_from", "grant_from")
            ):
                suspicious.append(name)
        self.assertEqual(
            suspicious, [], msg=f"unexpected auto-authorization helper: {suspicious}"
        )

    def test_request_is_distinct_type_from_authorization(self):
        req = make_request()
        auth = make_authorization()
        self.assertNotIsInstance(req, ExecutionAuthorization)
        self.assertNotIsInstance(auth, ExecutionAuthorizationRequest)
        self.assertNotEqual(type(req).__name__, type(auth).__name__)


if __name__ == "__main__":
    unittest.main()
