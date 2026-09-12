"""EA-4E.62B activation-authorization v2 contract qualification, fake only."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

import app
from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import _ready

from tools.hermes_core.production_activation_authorization import (
    ACTIVATION_AUTHORIZATION_ARTIFACT_VERSION,
    ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,
    AUTHORIZED,
    DENIED,
    ProductionActivationAuthorizationIssuer,
    ProductionActivationAuthorizationPolicy,
    ProductionActivationAuthorizationValidator,
    canonicalize_capability_scope,
)
from tools.hermes_core.production_activation_authorization_ceremony import (
    ProductionActivationAuthorizationCeremonyCoordinator,
    ProductionOperatorIdentity,
    ProductionOperatorIdentityVerifier,
)
from tools.hermes_core.production_activation_authorization_store import (
    ProductionActivationAuthStoreBootstrapper,
    ProductionActivationAuthorizationStore,
    ProductionActivationAuthorizationStoreError,
)
from tools.hermes_core.production_issuance import ClockCollaborator, QUALIFIED_RECEIVERS
from tools.hermes_core.receiver_dispatch import compute_ea4e7_authority_contract_id
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


NOW = "2026-09-10T12:00:00+00:00"
GOVERNING_COMMIT = "762f6246f67db7311dfd9a0ed64be541414d9e20"
OPERATOR_ID = "hermes-local-operator"
RECEIVER = "kilo-cli-agent"
CAPABILITY = ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE


@pytest.fixture(autouse=True)
def _reset_app_state(monkeypatch):
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_COMPONENTS", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_HOST", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_RECOVERY", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER", None)


class FakeBindingController:
    def __init__(self, receiver_id=RECEIVER, binding_id="binding-r62b"):
        self.receiver_id = receiver_id
        self.binding = SimpleNamespace(
            binding_id=binding_id,
            expires_at="2026-09-10T12:30:00+00:00",
        )
        self.teardown_calls = 0

    def get_binding_for_receiver(self, receiver_id):
        return self.binding if receiver_id == self.receiver_id else None

    def teardown(self, binding):
        assert binding is self.binding
        self.teardown_calls += 1
        self.binding = None
        return True


class FakeCredentialPreflight:
    def config_for(self, receiver_id, **values):
        return {"receiver_id": receiver_id, **values}

    def check(self, _config):
        return SimpleNamespace(ready=True, failure_code=None)


def _context(tmp_path, receiver_id=RECEIVER):
    store = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "activation-auth.sqlite3", bootstrap_explicit=True
    )
    clock = ClockCollaborator(now=NOW)
    verifier = ProductionOperatorIdentityVerifier(ProductionOperatorIdentity(OPERATOR_ID))
    bindings = FakeBindingController(receiver_id=receiver_id)
    policy = ProductionActivationAuthorizationPolicy(
        store=store,
        clock=clock,
        governing_commit=GOVERNING_COMMIT,
        readiness_status="PASS",
        operator_identity_verifier=verifier,
        binding_lookup=bindings.get_binding_for_receiver,
    )
    validator = ProductionActivationAuthorizationValidator(
        store=store,
        clock=clock,
        operator_identity_verifier=verifier,
        binding_lookup=bindings.get_binding_for_receiver,
    )
    ceremony = ProductionActivationAuthorizationCeremonyCoordinator(
        issuer=ProductionActivationAuthorizationIssuer(policy),
        binding_controller=bindings,
        operator_identity_verifier=verifier,
        clock=clock,
        credential_preflight=FakeCredentialPreflight(),
    )
    return store, clock, bindings, policy, validator, ceremony


def _request(receiver_id=RECEIVER, request_id="request-r62b", **changes):
    spec = QUALIFIED_RECEIVERS[receiver_id]
    values = {
        "request_id": request_id,
        "receiver_id": receiver_id,
        "governing_commit": GOVERNING_COMMIT,
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "authority_contract_id": compute_ea4e7_authority_contract_id(),
        "transport_contract_id": spec["transport_contract_id"],
        "model_binding_id": spec["model_binding_id"],
        "feature_gate_state": "ENABLED",
        "activation_mode": "ENABLED",
        "operator_intent": "EXPLICIT",
        "requested_ttl_seconds": 300,
        "nonce": f"nonce-{request_id}",
    }
    values.update(changes)
    return values


def _issue(tmp_path, receiver_id=RECEIVER, request_id="request-r62b", **changes):
    context = _context(tmp_path, receiver_id)
    result = context[-1].issue(_request(receiver_id, request_id, **changes))
    assert result.decision == AUTHORIZED
    assert result.artifact is not None
    return (*context, result.artifact)


def _claim(policy, validator, artifact, **changes):
    values = {
        "request_id": artifact.request_id,
        "receiver_id": artifact.receiver_id,
        "feature_gate_state": "ENABLED",
        "operator_id": artifact.operator_id,
        "executor_binding_id": artifact.executor_binding_id,
        "requested_capabilities": (CAPABILITY,),
    }
    values.update(changes)
    return policy.claim(artifact, validator=validator, **values)


def test_v2_artifact_binds_all_ceremony_authority_dimensions(tmp_path):
    store, _, bindings, _, _, _, artifact = _issue(tmp_path)
    store_id, store_epoch = store.lineage()
    assert artifact.artifact_version == ACTIVATION_AUTHORIZATION_ARTIFACT_VERSION == "2"
    assert artifact.ceremony_id.startswith("activation-ceremony-")
    assert artifact.operator_id == OPERATOR_ID
    assert artifact.activation_store_id == store_id
    assert artifact.activation_store_epoch == store_epoch
    assert artifact.executor_binding_id == bindings.binding.binding_id
    assert artifact.capability_scope == (CAPABILITY,)
    assert artifact.verify_hash()


def test_request_cannot_self_assert_trusted_ceremony_fields(tmp_path):
    _, _, _, _, _, _, artifact = _issue(
        tmp_path,
        ceremony_id="attacker-ceremony",
        operator_id="attacker",
        activation_store_id="attacker-store",
        activation_store_epoch=99,
        executor_binding_id="attacker-binding",
        capability_scope=("attacker.capability",),
    )
    assert artifact.ceremony_id != "attacker-ceremony"
    assert artifact.operator_id == OPERATOR_ID
    assert artifact.activation_store_id != "attacker-store"
    assert artifact.activation_store_epoch == 1
    assert artifact.executor_binding_id == "binding-r62b"
    assert artifact.capability_scope == (CAPABILITY,)


@pytest.mark.parametrize(
    ("scope", "reason"),
    [
        ((), None),
        (("*",), "WILDCARD_CAPABILITY_FORBIDDEN"),
        (("unknown",), "UNKNOWN_CAPABILITY"),
        ((CAPABILITY, "unknown"), "UNKNOWN_CAPABILITY"),
        (CAPABILITY, "CAPABILITY_SCOPE_MISSING"),
    ],
)
def test_capability_scope_rejects_noncanonical_authority(scope, reason):
    if scope == ():
        assert canonicalize_capability_scope(scope) == ()
        return
    with pytest.raises(ValueError) as exc:
        canonicalize_capability_scope(scope)
    assert str(exc.value) == reason


def test_capability_scope_is_deterministic_and_deduplicated():
    assert canonicalize_capability_scope((CAPABILITY, CAPABILITY)) == (CAPABILITY,)


@pytest.mark.parametrize(
    "field",
    [
        "ceremony_id",
        "operator_id",
        "activation_store_id",
        "activation_store_epoch",
        "executor_binding_id",
        "capability_scope",
    ],
)
def test_each_new_authority_field_is_hash_bound(tmp_path, field):
    _, _, _, _, validator, _, artifact = _issue(tmp_path)
    value = 99 if field == "activation_store_epoch" else ("unknown",) if field == "capability_scope" else "tampered"
    tampered = replace(artifact, **{field: value})
    result = validator.validate(
        tampered,
        request_id=artifact.request_id,
        receiver_id=artifact.receiver_id,
        governing_commit=GOVERNING_COMMIT,
        feature_gate_state="ENABLED",
    )
    assert result.valid is False


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"operator_id": "other"}, "OPERATOR_IDENTITY_MISMATCH"),
        ({"executor_binding_id": "other"}, "EXECUTOR_BINDING_ID_MISMATCH"),
        ({"requested_capabilities": ("unknown",)}, "UNKNOWN_CAPABILITY"),
    ],
)
def test_claim_uses_actual_operator_binding_and_capability(tmp_path, changes, reason):
    _, _, _, policy, validator, _, artifact = _issue(tmp_path)
    result = _claim(policy, validator, artifact, **changes)
    assert result.decision == DENIED
    assert result.reason == reason


def test_cross_store_authorization_is_denied_before_claim(tmp_path):
    store_a, _, _, _, _, _, artifact = _issue(tmp_path / "a")
    store_b, _, _, policy_b, validator_b, _ = _context(tmp_path / "b")
    result = _claim(policy_b, validator_b, artifact)
    assert result.reason == "ACTIVATION_STORE_ID_MISMATCH"
    assert store_a.state(artifact.activation_authorization_id) == "ISSUED"
    assert store_b.state(artifact.activation_authorization_id) is None


def test_cross_receiver_use_is_denied_before_claim(tmp_path):
    store, _, _, policy, validator, _, artifact = _issue(tmp_path)
    result = _claim(policy, validator, artifact, receiver_id="opencode-cli-agent")
    assert result.reason == "RECEIVER_MISMATCH"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


def test_missing_replaced_and_expired_bindings_fail_before_claim(tmp_path):
    store, _, bindings, policy, validator, _, artifact = _issue(tmp_path)
    bindings.binding = None
    assert _claim(policy, validator, artifact).reason == "EXECUTOR_BINDING_NOT_RESERVED"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"
    bindings.binding = SimpleNamespace(binding_id="replacement", expires_at="2026-09-10T12:30:00+00:00")
    assert _claim(policy, validator, artifact).reason == "EXECUTOR_BINDING_ID_MISMATCH"
    bindings.binding = SimpleNamespace(binding_id=artifact.executor_binding_id, expires_at=NOW)
    assert _claim(policy, validator, artifact).reason == "EXECUTOR_BINDING_EXPIRED"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


def test_store_identity_and_epoch_survive_restart(tmp_path):
    store = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "auth.sqlite3", bootstrap_explicit=True
    )
    lineage = store.lineage()
    assert ProductionActivationAuthorizationStore(store.path).lineage() == lineage


def test_bootstrap_refuses_to_replace_existing_store_or_anchor(tmp_path):
    path = tmp_path / "auth.sqlite3"
    bootstrapper = ProductionActivationAuthStoreBootstrapper()
    bootstrapper.bootstrap(path, bootstrap_explicit=True)
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        bootstrapper.bootstrap(path, bootstrap_explicit=True)
    assert exc.value.reason == "ACTIVATION_AUTH_STORE_ALREADY_EXISTS"


def test_missing_or_tampered_anchor_fails_closed(tmp_path):
    store = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "auth.sqlite3", bootstrap_explicit=True
    )
    anchor = Path(f"{store.path}.anchor")
    original = anchor.read_text(encoding="utf-8")
    anchor.unlink()
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ProductionActivationAuthorizationStore(store.path)
    assert exc.value.reason == "ACTIVATION_STORE_ANCHOR_MISSING"
    anchor.write_text(original.replace('"store_epoch": 1', '"store_epoch": 9'), encoding="utf-8")
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ProductionActivationAuthorizationStore(store.path)
    assert exc.value.reason == "ACTIVATION_STORE_ANCHOR_MISMATCH"


def test_store_clone_to_another_path_fails_closed(tmp_path):
    store = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "source.sqlite3", bootstrap_explicit=True
    )
    clone = tmp_path / "clone.sqlite3"
    clone_anchor = Path(f"{clone}.anchor")
    shutil.copy2(store.path, clone)
    shutil.copy2(Path(f"{store.path}.anchor"), clone_anchor)
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ProductionActivationAuthorizationStore(clone)
    assert exc.value.reason == "ACTIVATION_STORE_ANCHOR_MISMATCH"


def test_explicit_epoch_rotation_aborts_outstanding_and_invalidates_artifact(tmp_path):
    store, _, _, _, validator, _, artifact = _issue(tmp_path)
    assert store.rotate_epoch(rotate_explicit=True, now=NOW) == 2
    assert store.state(artifact.activation_authorization_id) == "ABORTED"
    assert ProductionActivationAuthorizationStore(store.path).lineage()[1] == 2
    result = validator.validate(
        artifact,
        request_id=artifact.request_id,
        receiver_id=artifact.receiver_id,
        governing_commit=GOVERNING_COMMIT,
        feature_gate_state="ENABLED",
    )
    assert result.reason == "ACTIVATION_STORE_EPOCH_MISMATCH"


def test_epoch_rotation_requires_explicit_intent(tmp_path):
    store = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "auth.sqlite3", bootstrap_explicit=True
    )
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        store.rotate_epoch(rotate_explicit=False, now=NOW)
    assert exc.value.reason == "ACTIVATION_STORE_ROTATION_NOT_EXPLICIT"


def test_old_database_restore_under_new_anchor_fails_closed(tmp_path):
    store = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "auth.sqlite3", bootstrap_explicit=True
    )
    old_database = tmp_path / "old.sqlite3"
    shutil.copy2(store.path, old_database)
    assert store.rotate_epoch(rotate_explicit=True, now=NOW) == 2
    shutil.copy2(old_database, store.path)
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ProductionActivationAuthorizationStore(store.path)
    assert exc.value.reason == "ACTIVATION_STORE_ANCHOR_MISMATCH"


def test_explicit_restore_preserves_lineage_rotates_and_terminalizes(tmp_path):
    source_store, _, _, _, _, _, artifact = _issue(tmp_path / "source")
    destination = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "destination" / "auth.sqlite3", bootstrap_explicit=True
    )
    destination_id, destination_epoch = destination.lineage()
    next_epoch = destination.restore_from_backup(
        source_store.path, restore_explicit=True, now=NOW
    )
    assert next_epoch == destination_epoch + 1
    assert destination.lineage() == (destination_id, next_epoch)
    assert destination.state(artifact.activation_authorization_id) == "ABORTED"
    restored = destination.load_artifact(artifact.activation_authorization_id)
    assert restored["activation_store_id"] != destination_id


def test_restore_requires_explicit_intent(tmp_path):
    source = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "source.sqlite3", bootstrap_explicit=True
    )
    destination = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "destination.sqlite3", bootstrap_explicit=True
    )
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        destination.restore_from_backup(
            source.path, restore_explicit=False, now=NOW
        )
    assert exc.value.reason == "ACTIVATION_STORE_RESTORE_NOT_EXPLICIT"


def test_explicit_v1_migration_terminalizes_legacy_outstanding_row(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE activation_auth_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO activation_auth_metadata VALUES ('schema_version', '1');
            CREATE TABLE production_activation_authorizations (
                activation_authorization_id TEXT PRIMARY KEY, request_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL, nonce TEXT NOT NULL UNIQUE,
                artifact_hash TEXT NOT NULL, artifact_json TEXT NOT NULL,
                state TEXT NOT NULL, issued_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE production_activation_authorization_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                activation_authorization_id TEXT, request_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL, event_type TEXT NOT NULL,
                created_at TEXT NOT NULL, detail TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO production_activation_authorizations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-auth", "legacy-request", RECEIVER, "legacy-nonce", "legacy-hash",
                json.dumps({"artifact_version": "1", "artifact_hash": "legacy-hash"}),
                "ISSUED", NOW, "2026-09-10T12:05:00+00:00", NOW,
            ),
        )
    bootstrapper = ProductionActivationAuthStoreBootstrapper()
    with pytest.raises(ProductionActivationAuthorizationStoreError):
        bootstrapper.bootstrap(path, bootstrap_explicit=True)
    migrated = bootstrapper.migrate_v1(
        path, migration_explicit=True, now=NOW
    )
    assert migrated.lineage()[1] == 1
    assert migrated.state("legacy-auth") == "ABORTED"
    assert migrated.load_artifact("legacy-auth")["artifact_version"] == "1"
    events = migrated.events_for_request("legacy-request")
    assert events[-1]["event_type"] == "ACTIVATION_AUTH_LEGACY_TERMINALIZED"


def test_v1_migration_requires_explicit_intent(tmp_path):
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ProductionActivationAuthStoreBootstrapper().migrate_v1(
            tmp_path / "missing.sqlite3", migration_explicit=False, now=NOW
        )
    assert exc.value.reason == "ACTIVATION_AUTH_STORE_MIGRATION_NOT_EXPLICIT"


def test_legacy_v1_artifact_is_retired_not_claimed(tmp_path):
    store, _, _, policy, validator, _, artifact = _issue(tmp_path)
    legacy = replace(artifact, artifact_version="1")
    result = _claim(policy, validator, legacy)
    assert result.decision == DENIED
    assert result.reason == "LEGACY_ACTIVATION_AUTHORIZATION_RETIRED"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


def test_cancel_is_atomic_durable_and_replay_safe(tmp_path):
    store, _, bindings, _, _, ceremony, artifact = _issue(tmp_path)
    assert ceremony.cancel(artifact.to_dict(), OPERATOR_ID, "OPERATOR_CANCELLED") == "CANCELLED"
    assert bindings.teardown_calls == 1
    assert ProductionActivationAuthorizationStore(store.path).state(
        artifact.activation_authorization_id
    ) == "CANCELLED"
    assert ceremony.cancel(
        artifact.to_dict(), OPERATOR_ID, "OPERATOR_CANCELLED"
    ) == "CANCELLED"
    assert bindings.teardown_calls == 1


def test_cancel_requires_the_trusted_operator(tmp_path):
    store, _, bindings, _, _, ceremony, artifact = _issue(tmp_path)
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ceremony.cancel(artifact.to_dict(), "request-asserted-operator", "OPERATOR_CANCELLED")
    assert exc.value.reason == "OPERATOR_IDENTITY_MISMATCH"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"
    assert bindings.teardown_calls == 0


def test_cancel_does_not_mutate_when_exact_binding_is_missing(tmp_path):
    store, _, bindings, _, _, ceremony, artifact = _issue(tmp_path)
    bindings.binding = None
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ceremony.cancel(artifact.to_dict(), OPERATOR_ID, "OPERATOR_CANCELLED")
    assert exc.value.reason == "EXECUTOR_BINDING_NOT_RESERVED"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


def test_cancel_rejects_tampered_artifact_and_unapproved_reason(tmp_path):
    store, _, _, _, _, ceremony, artifact = _issue(tmp_path)
    tampered = {**artifact.to_dict(), "request_id": "different"}
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ceremony.cancel(tampered, OPERATOR_ID, "OPERATOR_CANCELLED")
    assert exc.value.reason == "MALFORMED_REQUEST"
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ceremony.cancel(artifact.to_dict(), OPERATOR_ID, "free-form-text")
    assert exc.value.reason == "CANCELLATION_REVOCATION_REASON_INVALID"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


def test_claim_winner_requires_revoke_not_cancel(tmp_path):
    store, _, _, policy, validator, ceremony, artifact = _issue(tmp_path)
    assert _claim(policy, validator, artifact).decision == AUTHORIZED
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ceremony.cancel(artifact.to_dict(), OPERATOR_ID, "OPERATOR_CANCELLED")
    assert exc.value.reason == "CANCELLATION_NOT_ALLOWED_IN_STATE"
    assert store.state(artifact.activation_authorization_id) == "CLAIMED"


def test_cancel_winner_prevents_claim(tmp_path):
    store, _, bindings, policy, validator, ceremony, artifact = _issue(tmp_path)
    assert ceremony.cancel(artifact.to_dict(), OPERATOR_ID, "SCOPE_WITHDRAWN") == "CANCELLED"
    bindings.binding = SimpleNamespace(
        binding_id=artifact.executor_binding_id,
        expires_at="2026-09-10T12:30:00+00:00",
    )
    result = _claim(policy, validator, artifact)
    assert result.reason == "ACTIVATION_AUTH_CANCELLED"
    assert store.state(artifact.activation_authorization_id) == "CANCELLED"


def test_revoke_only_wins_from_claimed_and_is_restart_durable(tmp_path):
    store, _, bindings, policy, validator, ceremony, artifact = _issue(tmp_path)
    assert _claim(policy, validator, artifact).decision == AUTHORIZED
    assert ceremony.revoke(artifact.to_dict(), OPERATOR_ID, "SAFETY_HOLD") == "REVOKED"
    assert bindings.teardown_calls == 1
    reopened = ProductionActivationAuthorizationStore(store.path)
    assert reopened.state(artifact.activation_authorization_id) == "REVOKED"
    event_types = [item["event_type"] for item in reopened.ceremony_events(artifact.ceremony_id)]
    assert "ACTIVATION_AUTH_REVOKED" in event_types
    assert "CEREMONY_REVOKED" in event_types


def test_revoke_before_claim_is_denied_and_exact_replay_is_idempotent(tmp_path):
    store, _, bindings, policy, validator, ceremony, artifact = _issue(tmp_path)
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ceremony.revoke(artifact.to_dict(), OPERATOR_ID, "SAFETY_HOLD")
    assert exc.value.reason == "REVOCATION_NOT_ALLOWED_IN_STATE"
    assert _claim(policy, validator, artifact).decision == AUTHORIZED
    assert ceremony.revoke(artifact.to_dict(), OPERATOR_ID, "SAFETY_HOLD") == "REVOKED"
    assert ceremony.revoke(artifact.to_dict(), OPERATOR_ID, "SAFETY_HOLD") == "REVOKED"
    assert bindings.teardown_calls == 1
    assert store.state(artifact.activation_authorization_id) == "REVOKED"


def test_revoke_does_not_mutate_when_exact_binding_is_replaced(tmp_path):
    store, _, bindings, policy, validator, ceremony, artifact = _issue(tmp_path)
    assert _claim(policy, validator, artifact).decision == AUTHORIZED
    bindings.binding = SimpleNamespace(
        binding_id="replacement", expires_at="2026-09-10T12:30:00+00:00"
    )
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ceremony.revoke(artifact.to_dict(), OPERATOR_ID, "SAFETY_HOLD")
    assert exc.value.reason == "EXECUTOR_BINDING_ID_MISMATCH"
    assert store.state(artifact.activation_authorization_id) == "CLAIMED"


def test_revocation_cannot_rewrite_consumed_authorization(tmp_path):
    store, _, _, policy, validator, ceremony, artifact = _issue(tmp_path)
    assert _claim(policy, validator, artifact).decision == AUTHORIZED
    assert store.consume(artifact.activation_authorization_id, NOW) == "CONSUMED"
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ceremony.revoke(artifact.to_dict(), OPERATOR_ID, "SAFETY_HOLD")
    assert exc.value.reason == "REVOCATION_TOO_LATE"
    assert store.state(artifact.activation_authorization_id) == "CONSUMED"


@pytest.mark.parametrize(("terminal_action", "expected"), [("cancel", "CANCELLED"), ("revoke", "REVOKED")])
def test_recovery_observes_cancelled_and_revoked_as_terminal(tmp_path, terminal_action, expected):
    store, _, _, policy, validator, ceremony, artifact = _issue(tmp_path)
    if terminal_action == "cancel":
        ceremony.cancel(artifact.to_dict(), OPERATOR_ID, "OPERATOR_CANCELLED")
    else:
        assert _claim(policy, validator, artifact).decision == AUTHORIZED
        ceremony.revoke(artifact.to_dict(), OPERATOR_ID, "SAFETY_HOLD")
    assert store.abort(
        artifact.activation_authorization_id,
        NOW,
        recovery_request_id=artifact.request_id,
        recovery_receiver_id=artifact.receiver_id,
    ) == expected


def test_recovery_block_prevents_cancel_or_revoke(tmp_path):
    store, clock, bindings, _, validator, _ = _context(tmp_path)
    verifier = ProductionOperatorIdentityVerifier(ProductionOperatorIdentity(OPERATOR_ID))
    policy = ProductionActivationAuthorizationPolicy(
        store=store, clock=clock, governing_commit=GOVERNING_COMMIT,
        readiness_status="PASS", recovery_blocked=True,
        operator_identity_verifier=verifier,
        binding_lookup=bindings.get_binding_for_receiver,
    )
    ceremony = ProductionActivationAuthorizationCeremonyCoordinator(
        issuer=ProductionActivationAuthorizationIssuer(policy),
        binding_controller=bindings,
        operator_identity_verifier=verifier,
        clock=clock,
        credential_preflight=FakeCredentialPreflight(),
    )
    result = ceremony.issue(_request())
    assert result.decision == DENIED
    assert result.reason == "RECOVERY_BLOCKED"
    assert bindings.teardown_calls == 1


def test_mandatory_validation_audit_failure_prevents_claim(tmp_path, monkeypatch):
    store, _, _, policy, validator, _, artifact = _issue(tmp_path)

    def fail_audit(*_args, **_kwargs):
        raise ProductionActivationAuthorizationStoreError(
            "CEREMONY_AUDIT_PERSISTENCE_FAILURE"
        )

    monkeypatch.setattr(store, "record_ceremony_event", fail_audit)
    result = _claim(policy, validator, artifact)
    assert result.reason == "CEREMONY_AUDIT_PERSISTENCE_FAILURE"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


def test_ceremony_audit_has_durable_issue_order(tmp_path):
    store, _, _, _, _, _, artifact = _issue(tmp_path)
    events = [item["event_type"] for item in store.ceremony_events(artifact.ceremony_id)]
    assert events == [
        "CEREMONY_REQUESTED",
        "OPERATOR_IDENTITY_VERIFIED",
        "STORE_LINEAGE_VERIFIED",
        "CEREMONY_PREFLIGHT_PASSED",
        "CEREMONY_BINDING_RESERVED",
        "ACTIVATION_AUTH_ISSUED",
    ]
    assert store.ceremony_state(artifact.ceremony_id) == "ISSUED"


def test_audit_owner_cannot_mark_unconsumed_authorization_complete(tmp_path):
    store, _, _, _, _, ceremony, artifact = _issue(tmp_path)
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ceremony.complete(artifact, success=True)
    assert exc.value.reason == "CEREMONY_STATE_MISMATCH"
    assert store.ceremony_state(artifact.ceremony_id) == "ISSUED"


def test_preflight_denial_is_correlated_and_releases_reserved_binding(tmp_path):
    store, _, bindings, _, _, ceremony = _context(tmp_path)
    ceremony._preflight = SimpleNamespace(
        config_for=lambda *_args, **_kwargs: {},
        check=lambda _config: SimpleNamespace(ready=False, failure_code="CREDENTIAL_VALUE_ABSENT"),
    )
    result = ceremony.issue(_request(request_id="preflight-denied"))
    assert result.decision == DENIED
    assert result.reason == "CREDENTIAL_PREFLIGHT_DENIED:CREDENTIAL_VALUE_ABSENT"
    assert bindings.teardown_calls == 1
    events = store.events_for_request("preflight-denied")
    assert [item["event_type"] for item in events] == [
        "ACTIVATION_AUTH_REQUESTED", "ACTIVATION_AUTH_DENIED"
    ]


def test_stale_commit_is_denied_and_releases_binding(tmp_path):
    store, _, bindings, _, _, ceremony = _context(tmp_path)
    result = ceremony.issue(_request(governing_commit="stale-parent"))
    assert result.decision == DENIED
    assert result.reason == "COMMIT_MISMATCH"
    assert bindings.teardown_calls == 1
    assert store.has_outstanding() is False


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_full_fake_v2_app_ceremony_consumes_executes_fake_and_tears_down(
    tmp_path, receiver_id
):
    components, fake, payload = _ready(
        tmp_path, receiver_id, f"ea4e62b-full-{receiver_id}"
    )
    artifact = payload["activation_authorization"]
    store = app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER._policy.store
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    assert fake.calls == 1
    assert store.state(artifact["activation_authorization_id"]) == "CONSUMED"
    assert components.composition.binding_controller.active_binding_count == 0
    event_types = [
        item["event_type"] for item in store.ceremony_events(artifact["ceremony_id"])
    ]
    assert event_types == [
        "CEREMONY_REQUESTED", "OPERATOR_IDENTITY_VERIFIED",
        "STORE_LINEAGE_VERIFIED", "CEREMONY_PREFLIGHT_PASSED",
        "CEREMONY_BINDING_RESERVED", "ACTIVATION_AUTH_ISSUED",
        "ACTIVATION_AUTH_VALIDATED", "ACTIVATION_AUTH_CLAIMED",
        "PRODUCTION_ACTIVATION_ENTERED", "ACTIVATION_AUTH_CONSUMED",
        "PRODUCTION_ACTIVATION_EXITED", "BINDING_RELEASED",
        "CEREMONY_COMPLETED",
    ]
    assert store.ceremony_state(artifact["ceremony_id"]) == "COMPLETED"


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_both_qualified_receivers_issue_under_the_same_v2_contract(tmp_path, receiver_id):
    _, _, _, _, _, _, artifact = _issue(tmp_path, receiver_id=receiver_id)
    assert artifact.receiver_id == receiver_id
    assert artifact.artifact_version == "2"


def test_grok_remains_denied_without_creating_a_ceremony(tmp_path):
    _, _, _, _, _, ceremony = _context(tmp_path)
    result = ceremony.issue({"receiver_id": "grok", "request_id": "grok-request"})
    assert result.decision == DENIED
    assert result.reason == "EXECUTOR_BINDING_ID_MISSING"


def test_production_modules_remain_non_live_by_static_surface():
    root = Path(__file__).resolve().parents[2] / "tools" / "hermes_core"
    files = [
        root / "production_activation_authorization.py",
        root / "production_activation_authorization_store.py",
        root / "production_activation_authorization_ceremony.py",
    ]
    forbidden = ("subprocess", "requests.", "urllib", "playwright", "comfyui", "cuda", "mcp")
    combined = "\n".join(path.read_text(encoding="utf-8").casefold() for path in files)
    assert all(token not in combined for token in forbidden)


def test_anchor_contains_no_secret_material(tmp_path):
    store = ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "auth.sqlite3", bootstrap_explicit=True
    )
    anchor = json.loads(Path(f"{store.path}.anchor").read_text(encoding="utf-8"))
    assert set(anchor) == {
        "schema_id",
        "store_id",
        "store_epoch",
        "installation_id",
        "store_path_hash",
        "anchor_hash",
    }
    assert not any("secret" in key.casefold() or "token" in key.casefold() for key in anchor)
