from __future__ import annotations

import inspect
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.hermes_core import run_r12e_live_proof as live_proof
from tests.hermes_core.test_execution_launch_admission import _build_canonical_chain
from tools.hermes_core.lease_window import (
    EXPIRY_SEMANTICS,
    LEASE_WINDOW_MANIFEST,
    LEASE_WINDOW_POLICY_VERSION,
    MAX_TTL_SECONDS,
    QUALIFIED_LEASE_WINDOW_POLICY,
    QUALIFIED_LEASE_WINDOW_POLICY_ID,
    AttemptLeaseWindow,
    LeaseWindowError,
    LeaseWindowPolicy,
    is_lease_valid,
    issue_attempt_lease_window,
    issue_or_load_attempt_lease_window,
    lease_event_time,
    lease_window_policy_id,
    lease_window_policy_material,
    load_attempt_lease_window,
    require_lease_valid,
)


OWNER = "a" * 64
FIXED = datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc)


def clock_at(value):
    return lambda: value


class LeaseWindowPolicyTests(unittest.TestCase):
    def test_qualified_policy_is_deterministic(self):
        self.assertEqual(
            QUALIFIED_LEASE_WINDOW_POLICY_ID,
            lease_window_policy_id(QUALIFIED_LEASE_WINDOW_POLICY.material()),
        )
        self.assertEqual(
            QUALIFIED_LEASE_WINDOW_POLICY_ID,
            LeaseWindowPolicy().policy_id,
        )

    def test_same_rules_have_same_policy_id(self):
        self.assertEqual(LeaseWindowPolicy(300).policy_id, LeaseWindowPolicy(300).policy_id)

    def test_ttl_change_changes_policy_id(self):
        self.assertNotEqual(LeaseWindowPolicy(300).policy_id, LeaseWindowPolicy(301).policy_id)

    def test_expiry_semantics_change_changes_policy_id(self):
        changed = lease_window_policy_material(expiry_semantics="valid-through-expiry")
        self.assertNotEqual(QUALIFIED_LEASE_WINDOW_POLICY_ID, lease_window_policy_id(changed))

    def test_policy_material_is_finite_strict_and_nonrenewing(self):
        material = QUALIFIED_LEASE_WINDOW_POLICY.material()
        self.assertEqual(material["policy_version"], LEASE_WINDOW_POLICY_VERSION)
        self.assertEqual(material["expiry_semantics"], EXPIRY_SEMANTICS)
        self.assertEqual(material["clock_skew_grace_seconds"], 0)
        self.assertFalse(material["auto_renewal"])
        self.assertLessEqual(material["ttl_seconds"], MAX_TTL_SECONDS)

    def test_invalid_ttl_is_rejected(self):
        for value in (True, 0, -1, MAX_TTL_SECONDS + 1, 1.5, None):
            with self.subTest(value=value), self.assertRaises(LeaseWindowError):
                LeaseWindowPolicy(value)

    def test_environment_cannot_override_policy(self):
        old = os.environ.get("HERMES_LEASE_TTL_SECONDS")
        os.environ["HERMES_LEASE_TTL_SECONDS"] = "999999"
        try:
            self.assertEqual(LeaseWindowPolicy().ttl_seconds, 300)
        finally:
            if old is None:
                os.environ.pop("HERMES_LEASE_TTL_SECONDS", None)
            else:
                os.environ["HERMES_LEASE_TTL_SECONDS"] = old

    def test_issuance_has_no_caller_expiry_parameter(self):
        self.assertNotIn("expires_at", inspect.signature(issue_attempt_lease_window).parameters)
        with self.assertRaises(TypeError):
            issue_attempt_lease_window(
                LeaseWindowPolicy(), OWNER,
                clock=clock_at(FIXED), expires_at="2099-01-01T00:00:00Z",
            )


class LeaseWindowInstanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.namespace = Path(self.tmp.name) / "proof-fake"
        self.namespace.mkdir()
        self.policy = LeaseWindowPolicy()

    def tearDown(self):
        self.tmp.cleanup()

    def issue(self):
        return issue_or_load_attempt_lease_window(
            self.namespace, self.policy, OWNER, clock=clock_at(FIXED),
        )

    def test_fixed_clock_derives_exact_bounded_utc_window(self):
        window = issue_attempt_lease_window(self.policy, OWNER, clock=clock_at(FIXED))
        self.assertEqual(window.issued_at, "2026-08-31T14:00:00Z")
        self.assertEqual(window.expires_at, "2026-08-31T14:05:00Z")
        self.assertTrue(window.issued_at.endswith("Z"))
        self.assertTrue(window.expires_at.endswith("Z"))

    def test_event_times_must_stay_inside_window(self):
        window = issue_attempt_lease_window(self.policy, OWNER, clock=clock_at(FIXED))
        self.assertEqual(lease_event_time(window, 4), "2026-08-31T14:00:04Z")
        for offset in (-1, 300):
            with self.subTest(offset=offset), self.assertRaises(LeaseWindowError):
                lease_event_time(window, offset)

    def test_validity_is_fail_closed_at_exact_expiry(self):
        window = issue_attempt_lease_window(self.policy, OWNER, clock=clock_at(FIXED))
        self.assertTrue(is_lease_valid(window, clock=clock_at(FIXED)))
        self.assertTrue(is_lease_valid(
            window, clock=clock_at(FIXED + timedelta(seconds=299, microseconds=999999)),
        ))
        self.assertFalse(is_lease_valid(
            window, clock=clock_at(FIXED + timedelta(seconds=300)),
        ))
        self.assertFalse(is_lease_valid(
            window, clock=clock_at(FIXED + timedelta(seconds=301)),
        ))

    def test_backward_clock_does_not_create_authority(self):
        window = issue_attempt_lease_window(self.policy, OWNER, clock=clock_at(FIXED))
        self.assertFalse(is_lease_valid(
            window, clock=clock_at(FIXED - timedelta(seconds=1)),
        ))

    def test_naive_clock_is_rejected(self):
        naive = datetime(2026, 8, 31, 14, 0, 0)
        with self.assertRaises(LeaseWindowError):
            issue_attempt_lease_window(self.policy, OWNER, clock=clock_at(naive))

    def test_persisted_replay_preserves_exact_timestamps(self):
        first = self.issue()
        second = issue_or_load_attempt_lease_window(
            self.namespace,
            self.policy,
            OWNER,
            clock=clock_at(FIXED + timedelta(days=30)),
        )
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(first.window, second.window)
        self.assertEqual(first.window.artifact_hash, second.window.artifact_hash)

    def test_restart_before_expiry_recovers_same_lease(self):
        first = self.issue()
        replay = load_attempt_lease_window(self.namespace, self.policy, OWNER)
        self.assertEqual(first.window, replay.window)
        self.assertTrue(is_lease_valid(
            replay.window, clock=clock_at(FIXED + timedelta(seconds=120)),
        ))

    def test_restart_after_expiry_remains_expired(self):
        first = self.issue()
        replay = issue_or_load_attempt_lease_window(
            self.namespace,
            self.policy,
            OWNER,
            clock=clock_at(FIXED + timedelta(days=1)),
        )
        self.assertEqual(first.window, replay.window)
        with self.assertRaises(LeaseWindowError):
            require_lease_valid(
                replay.window, clock=clock_at(FIXED + timedelta(days=1)),
            )

    def test_manifest_freezes_policy_owner_and_artifact_hash(self):
        reservation = self.issue()
        manifest = json.loads(reservation.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(reservation.manifest_path.name, LEASE_WINDOW_MANIFEST)
        self.assertEqual(manifest["policy_id"], self.policy.policy_id)
        self.assertEqual(manifest["namespace_owner_hash"], OWNER)
        self.assertEqual(manifest["artifact_hash"], reservation.window.artifact_hash)
        self.assertFalse(manifest["policy"]["auto_renewal"])

    def test_foreign_owner_policy_and_tamper_are_rejected(self):
        reservation = self.issue()
        with self.assertRaises(LeaseWindowError):
            load_attempt_lease_window(self.namespace, self.policy, "b" * 64)
        with self.assertRaises(LeaseWindowError):
            load_attempt_lease_window(self.namespace, LeaseWindowPolicy(301), OWNER)
        manifest = json.loads(reservation.manifest_path.read_text(encoding="utf-8"))
        manifest["expires_at"] = "2026-08-31T14:06:00Z"
        reservation.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(LeaseWindowError):
            load_attempt_lease_window(self.namespace, self.policy, OWNER)

    def test_missing_or_malformed_manifest_is_rejected(self):
        with self.assertRaises(LeaseWindowError):
            load_attempt_lease_window(self.namespace, self.policy, OWNER)
        (self.namespace / LEASE_WINDOW_MANIFEST).write_text("not json", encoding="utf-8")
        with self.assertRaises(LeaseWindowError):
            load_attempt_lease_window(self.namespace, self.policy, OWNER)

    def test_namespace_must_preexist(self):
        with self.assertRaises(LeaseWindowError):
            issue_or_load_attempt_lease_window(
                self.namespace / "missing", self.policy, OWNER, clock=clock_at(FIXED),
            )


class LeaseWindowRegressionTests(unittest.TestCase):
    def test_historical_expired_r6_fixture_still_denies_capability(self):
        stale = AttemptLeaseWindow(
            policy_id=QUALIFIED_LEASE_WINDOW_POLICY_ID,
            namespace_owner_hash=OWNER,
            issued_at="2026-08-30T23:54:59Z",
            expires_at="2026-08-30T23:59:59Z",
        )
        observed = datetime(2026, 8, 31, 13, 11, 30, tzinfo=timezone.utc)
        self.assertFalse(is_lease_valid(stale, clock=clock_at(observed)))
        with self.assertRaises(LeaseWindowError):
            require_lease_valid(stale, clock=clock_at(observed))

    def test_fresh_fake_attempt_is_eligible_without_process(self):
        window = issue_attempt_lease_window(
            QUALIFIED_LEASE_WINDOW_POLICY, OWNER, clock=clock_at(FIXED),
        )
        self.assertTrue(is_lease_valid(
            window, clock=clock_at(FIXED + timedelta(seconds=1)),
        ))

    def test_live_harness_uses_persisted_policy_not_fixed_calendar_deadline(self):
        source = Path(live_proof.__file__).read_text(encoding="utf-8")
        self.assertNotIn("DEADLINE =", source)
        self.assertNotIn("2026-08-30T23:59:59Z", source)
        self.assertIn("issue_or_load_attempt_lease_window", source)
        self.assertIn("load_attempt_lease_window", source)
        self.assertIn("require_lease_valid(lease_window.window)", source)
        self.assertEqual(live_proof.LEASE_POLICY.policy_id, QUALIFIED_LEASE_WINDOW_POLICY_ID)

    def test_fresh_window_anchors_canonical_authority_chain(self):
        window = issue_attempt_lease_window(
            QUALIFIED_LEASE_WINDOW_POLICY, OWNER, clock=clock_at(FIXED),
        )
        chain = _build_canonical_chain(
            seed="r6d-fake",
            issued_at=window.issued_at,
            deadline=window.expires_at,
        )
        self.assertEqual(chain.authorization.issued_at, window.issued_at)
        self.assertEqual(chain.authorization.expires_at, window.expires_at)
        self.assertEqual(chain.claim.claim_expires_at, window.expires_at)
        self.assertEqual(chain.attempt.must_start_by, window.expires_at)
        self.assertEqual(chain.route.must_start_by, window.expires_at)


if __name__ == "__main__":
    unittest.main()
