"""EA-4E.60 explicit production-activation authorization, fake only."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import app
from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import (
    FakeQualifiedExecutor,
    _bind,
    _bootstrap_store,
    _configure,
    _ready,
)
from tools.hermes_core.production_app_config import ProductionAppRuntimeConfig
from tools.hermes_core.production_executor_binding import ExecutorRegistry
from tools.hermes_core.production_activation import ProductionActivationValidator
from tools.hermes_core.production_activation_authorization import (
    ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,
    ACTIVATION_AUTHORIZATION_SCHEMA_ID,
    AUTHORIZED,
    DENIED,
    ProductionActivationAuthorizationIssuer,
    ProductionActivationAuthorizationPolicy,
    ProductionActivationAuthorizationRequest,
    ProductionActivationAuthorizationValidator,
    ProductionAppActivationTransitionOwner,
)
from tools.hermes_core.production_activation_authorization_ceremony import (
    ProductionOperatorIdentity,
    ProductionOperatorIdentityVerifier,
)
from tools.hermes_core.production_activation_authorization_store import (
    ProductionActivationAuthStoreBootstrapper,
    ProductionActivationAuthorizationStore,
    ProductionActivationAuthorizationStoreError,
)
from tools.hermes_core.production_issuance import ClockCollaborator, QUALIFIED_RECEIVERS
from tools.hermes_core.production_wiring import ProductionWiringConfig
from tools.hermes_core.receiver_dispatch import compute_ea4e7_authority_contract_id
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


NOW = "2026-01-01T00:00:00+00:00"
GOVERNING_COMMIT = "d61945f96e11b19ef0dcbd008c4d301647c8acad"
RECEIVER = "kilo-cli-agent"
OPERATOR_ID = "ea4e60-local-operator"
TEST_BINDING_ID = "binding-ea4e60-fake"


@pytest.fixture(autouse=True)
def _reset_app_activation_state(monkeypatch):
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_COMPONENTS", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_HOST", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_RECOVERY", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER", None)


def _store(tmp_path):
    return ProductionActivationAuthStoreBootstrapper().bootstrap(
        tmp_path / "activation-auth.sqlite3", bootstrap_explicit=True
    )


def _request(store, request_id="request-1", **changes):
    spec = QUALIFIED_RECEIVERS[RECEIVER]
    store_id, store_epoch = store.lineage()
    values = {
        "request_id": request_id,
        "receiver_id": RECEIVER,
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
        "ceremony_id": f"ceremony-{request_id}",
        "operator_id": OPERATOR_ID,
        "activation_store_id": store_id,
        "activation_store_epoch": store_epoch,
        "executor_binding_id": TEST_BINDING_ID,
        "capability_scope": (ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,),
    }
    values.update(changes)
    return ProductionActivationAuthorizationRequest(**values)


def _collaborators(tmp_path, *, now=NOW, readiness="PASS", recovery_blocked=False):
    store = _store(tmp_path)
    clock = ClockCollaborator(now=now)
    policy = ProductionActivationAuthorizationPolicy(
        store=store,
        clock=clock,
        governing_commit=GOVERNING_COMMIT,
        readiness_status=readiness,
        recovery_blocked=recovery_blocked,
        operator_identity_verifier=ProductionOperatorIdentityVerifier(
            ProductionOperatorIdentity(OPERATOR_ID)
        ),
        binding_lookup=lambda _receiver: SimpleNamespace(
            binding_id=TEST_BINDING_ID,
            expires_at="2026-01-01T00:30:00+00:00",
        ),
    )
    return store, clock, policy, ProductionActivationAuthorizationIssuer(policy)


def _issue(tmp_path, request_id="request-1"):
    store, clock, policy, issuer = _collaborators(tmp_path)
    result = issuer.issue(_request(store, request_id))
    assert result.decision == AUTHORIZED
    assert result.artifact is not None
    return store, clock, policy, result.artifact


def _claim(store, clock, policy, artifact):
    validator = ProductionActivationAuthorizationValidator(store=store, clock=clock)
    return policy.claim(
        artifact,
        validator=validator,
        request_id=artifact.request_id,
        receiver_id=artifact.receiver_id,
        feature_gate_state="ENABLED",
    )


def test_store_bootstrap_is_explicit(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(ProductionActivationAuthorizationStoreError):
        ProductionActivationAuthorizationStore(path)
    with pytest.raises(ProductionActivationAuthorizationStoreError):
        ProductionActivationAuthStoreBootstrapper().bootstrap(
            path, bootstrap_explicit=False
        )


def test_issue_persists_immutable_request_bound_artifact_and_stops(tmp_path):
    store, _, _, artifact = _issue(tmp_path)
    assert artifact.schema_id == ACTIVATION_AUTHORIZATION_SCHEMA_ID
    assert artifact.request_id == "request-1"
    assert artifact.governing_commit == GOVERNING_COMMIT
    assert artifact.verify_hash()
    assert store.state(artifact.activation_authorization_id) == "ISSUED"
    assert [e["event_type"] for e in store.events_for_request("request-1")] == [
        "ACTIVATION_AUTH_REQUESTED",
        "ACTIVATION_AUTH_ISSUED",
    ]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"operator_intent": ""}, "MALFORMED_REQUEST"),
        ({"operator_intent": "IMPLICIT"}, "OPERATOR_INTENT_MISSING"),
        ({"feature_gate_state": "DISABLED"}, "FEATURE_GATE_DISABLED"),
        ({"governing_commit": "wrong"}, "COMMIT_MISMATCH"),
        ({"router_contract_id": "wrong"}, "ROUTER_CONTRACT_MISMATCH"),
        ({"authority_contract_id": "wrong"}, "AUTHORITY_CONTRACT_MISMATCH"),
        ({"transport_contract_id": "wrong"}, "TRANSPORT_BINDING_MISMATCH"),
        ({"model_binding_id": "wrong"}, "MODEL_BINDING_MISMATCH"),
        ({"nonce": ""}, "MALFORMED_REQUEST"),
        ({"requested_ttl_seconds": 0}, "MALFORMED_REQUEST"),
        ({"requested_ttl_seconds": 301}, "MALFORMED_REQUEST"),
    ],
)
def test_issue_policy_denies_invalid_requests_without_issuing(tmp_path, changes, reason):
    store, _, _, issuer = _collaborators(tmp_path)
    result = issuer.issue(_request(store, **changes))
    assert result.decision == DENIED
    assert result.reason == reason
    assert result.artifact is None
    assert not store.has_outstanding()


def test_grok_is_denied_without_fallback(tmp_path):
    store, _, _, issuer = _collaborators(tmp_path)
    result = issuer.issue(_request(store, receiver_id="grok-agent"))
    assert result.decision == DENIED
    assert result.reason == "UNSUPPORTED_RECEIVER"
    assert not store.has_outstanding()


@pytest.mark.parametrize(
    ("readiness", "recovery_blocked", "reason"),
    [("HOLD", False, "READINESS_NOT_PASS"), ("PASS", True, "RECOVERY_BLOCKED")],
)
def test_trusted_policy_state_denies_issue(
    tmp_path, readiness, recovery_blocked, reason
):
    store, _, _, issuer = _collaborators(
        tmp_path, readiness=readiness, recovery_blocked=recovery_blocked
    )
    result = issuer.issue(_request(store))
    assert result.decision == DENIED
    assert result.reason == reason
    assert not store.has_outstanding()


def test_one_outstanding_authorization_is_allowed(tmp_path):
    store, _, _, issuer = _collaborators(tmp_path)
    first = issuer.issue(_request(store, "first"))
    second = issuer.issue(_request(store, "second"))
    assert first.decision == AUTHORIZED
    assert second.decision == DENIED
    assert second.reason == "CONFLICTING_OUTSTANDING_AUTH"
    assert store.state(first.artifact.activation_authorization_id) == "ISSUED"


def test_validator_is_nonmutating_and_tamper_fails_closed(tmp_path):
    store, clock, _, artifact = _issue(tmp_path)
    validator = ProductionActivationAuthorizationValidator(store=store, clock=clock)
    result = validator.validate(
        replace(artifact, receiver_id="opencode-cli-agent"),
        request_id=artifact.request_id,
        receiver_id=RECEIVER,
        governing_commit=GOVERNING_COMMIT,
        feature_gate_state="ENABLED",
    )
    assert not result.valid
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("request_id", "different-request", "REQUEST_ID_MISMATCH"),
        ("receiver_id", "opencode-cli-agent", "RECEIVER_MISMATCH"),
        ("governing_commit", "different-commit", "COMMIT_MISMATCH"),
        ("feature_gate_state", "DISABLED", "FEATURE_GATE_DISABLED"),
    ],
)
def test_validator_denies_wrong_request_scope_without_claim(
    tmp_path, field, value, reason
):
    store, clock, _, artifact = _issue(tmp_path)
    context = {
        "request_id": artifact.request_id,
        "receiver_id": artifact.receiver_id,
        "governing_commit": artifact.governing_commit,
        "feature_gate_state": "ENABLED",
    }
    context[field] = value
    result = ProductionActivationAuthorizationValidator(
        store=store, clock=clock
    ).validate(artifact, **context)
    assert not result.valid
    assert result.reason == reason
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


def test_expired_authorization_is_denied_before_claim(tmp_path):
    store, _, policy, artifact = _issue(tmp_path)
    late_clock = ClockCollaborator(now=artifact.expires_at)
    validator = ProductionActivationAuthorizationValidator(store=store, clock=late_clock)
    claim = policy.claim(
        artifact,
        validator=validator,
        request_id=artifact.request_id,
        receiver_id=RECEIVER,
        feature_gate_state="ENABLED",
    )
    assert claim.decision == DENIED
    assert claim.reason == "EXPIRED"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


def test_claim_is_atomic_single_use_and_replay_survives_reopen(tmp_path):
    store, clock, policy, artifact = _issue(tmp_path)
    first = _claim(store, clock, policy, artifact)
    second = _claim(store, clock, policy, artifact)
    reopened = ProductionActivationAuthorizationStore(store.path)
    assert first.state == "CLAIMED"
    assert second.decision == DENIED
    assert second.reason == "REPLAY"
    assert reopened.state(artifact.activation_authorization_id) == "CLAIMED"


def test_successful_transition_consumes_then_teardown_clears_activation(tmp_path):
    store, clock, policy, artifact = _issue(tmp_path)
    claim = _claim(store, clock, policy, artifact)
    _, activation = external_authority_and_activation(
        RECEIVER, artifact.request_id, clock=clock
    )
    owner = ProductionAppActivationTransitionOwner(
        store=store,
        clock=clock,
        activation_validator=ProductionActivationValidator(
            router_contract_id=compute_ea4e6_router_contract_id()
        ),
    )
    result = owner.transition(
        request_id=artifact.request_id,
        receiver_id=RECEIVER,
        claimed_authorization=claim,
        production_activation=activation,
    )
    assert result.decision == AUTHORIZED
    assert result.durable_authorization_state == "CONSUMED"
    assert owner.is_active(artifact.request_id)
    assert owner.teardown(artifact.request_id)
    assert not owner.is_active(artifact.request_id)
    assert ProductionActivationAuthorizationStore(store.path).state(
        artifact.activation_authorization_id
    ) == "CONSUMED"


def test_invalid_activation_aborts_claim_without_execution(tmp_path):
    store, clock, policy, artifact = _issue(tmp_path)
    claim = _claim(store, clock, policy, artifact)
    owner = ProductionAppActivationTransitionOwner(
        store=store,
        clock=clock,
        activation_validator=ProductionActivationValidator(
            router_contract_id=compute_ea4e6_router_contract_id()
        ),
    )
    result = owner.transition(
        request_id=artifact.request_id,
        receiver_id=RECEIVER,
        claimed_authorization=claim,
        production_activation=None,
    )
    assert result.decision == DENIED
    assert result.durable_authorization_state == "ABORTED"
    assert not owner.is_active(artifact.request_id)
    assert store.state(artifact.activation_authorization_id) == "ABORTED"


def test_aborted_authorization_cannot_replay_after_reopen(tmp_path):
    store, clock, policy, artifact = _issue(tmp_path)
    claim = _claim(store, clock, policy, artifact)
    store.abort(artifact.activation_authorization_id, clock.now_iso())
    reopened = ProductionActivationAuthorizationStore(store.path)
    replay = _claim(reopened, clock, policy, artifact)
    assert reopened.state(artifact.activation_authorization_id) == "ABORTED"
    assert replay.decision == DENIED
    assert replay.reason == "REPLAY"


def test_consumed_authorization_cannot_replay_after_reopen(tmp_path):
    store, clock, policy, artifact = _issue(tmp_path)
    _claim(store, clock, policy, artifact)
    store.consume(artifact.activation_authorization_id, clock.now_iso())
    reopened = ProductionActivationAuthorizationStore(store.path)
    reopened_policy = ProductionActivationAuthorizationPolicy(
        store=reopened,
        clock=clock,
        governing_commit=GOVERNING_COMMIT,
        readiness_status="PASS",
    )
    replay = _claim(reopened, clock, reopened_policy, artifact)
    assert reopened.state(artifact.activation_authorization_id) == "CONSUMED"
    assert replay.decision == DENIED
    assert replay.reason == "REPLAY"


def test_fresh_explicit_request_can_follow_expired_authorization(tmp_path):
    store, _, _, first = _issue(tmp_path, "expired-first")
    late_clock = ClockCollaborator(now=first.expires_at)
    policy = ProductionActivationAuthorizationPolicy(
        store=store,
        clock=late_clock,
        governing_commit=GOVERNING_COMMIT,
        readiness_status="PASS",
        operator_identity_verifier=ProductionOperatorIdentityVerifier(
            ProductionOperatorIdentity(OPERATOR_ID)
        ),
        binding_lookup=lambda _receiver: SimpleNamespace(
            binding_id=TEST_BINDING_ID,
            expires_at="2026-01-01T01:30:00+00:00",
        ),
    )
    second = ProductionActivationAuthorizationIssuer(policy).issue(
        _request(store, "fresh-second")
    )
    assert store.state(first.activation_authorization_id) == "EXPIRED"
    assert second.decision == AUTHORIZED
    assert store.state(second.artifact.activation_authorization_id) == "ISSUED"


def test_authorization_is_not_transferable_between_receivers(tmp_path):
    store, clock, _, artifact = _issue(tmp_path)
    validator = ProductionActivationAuthorizationValidator(store=store, clock=clock)
    result = validator.validate(
        artifact,
        request_id=artifact.request_id,
        receiver_id="opencode-cli-agent",
        governing_commit=GOVERNING_COMMIT,
        feature_gate_state="ENABLED",
    )
    assert not result.valid
    assert result.reason == "RECEIVER_MISMATCH"
    assert store.state(artifact.activation_authorization_id) == "ISSUED"


def test_consume_persistence_failure_clears_activation_and_marks_recovery(tmp_path, monkeypatch):
    store, clock, policy, artifact = _issue(tmp_path)
    claim = _claim(store, clock, policy, artifact)
    _, activation = external_authority_and_activation(
        RECEIVER, artifact.request_id, clock=clock
    )
    recovery = []
    owner = ProductionAppActivationTransitionOwner(
        store=store,
        clock=clock,
        activation_validator=ProductionActivationValidator(
            router_contract_id=compute_ea4e6_router_contract_id()
        ),
        recovery_marker=recovery.append,
    )

    def fail_consume(*_args, **_kwargs):
        raise ProductionActivationAuthorizationStoreError("CONSUME_PERSISTENCE_FAILED")

    monkeypatch.setattr(store, "consume", fail_consume)
    result = owner.transition(
        request_id=artifact.request_id,
        receiver_id=RECEIVER,
        claimed_authorization=claim,
        production_activation=activation,
    )
    assert result.decision == DENIED
    assert result.recovery_required
    assert not owner.is_active(artifact.request_id)
    assert recovery == [artifact.request_id]


def test_mandatory_enter_event_failure_fails_closed(
    tmp_path, monkeypatch
):
    store, clock, policy, artifact = _issue(tmp_path)
    claim = _claim(store, clock, policy, artifact)
    _, activation = external_authority_and_activation(
        RECEIVER, artifact.request_id, clock=clock
    )
    owner = ProductionAppActivationTransitionOwner(
        store=store,
        clock=clock,
        activation_validator=ProductionActivationValidator(
            router_contract_id=compute_ea4e6_router_contract_id()
        ),
    )

    def fail_event(*_args, **_kwargs):
        raise ProductionActivationAuthorizationStoreError("ACCOUNTING_FAILED")

    monkeypatch.setattr(store, "record_activation_event", fail_event)
    result = owner.transition(
        request_id=artifact.request_id,
        receiver_id=RECEIVER,
        claimed_authorization=claim,
        production_activation=activation,
    )
    assert result.decision == DENIED
    assert result.reason == "CEREMONY_AUDIT_PERSISTENCE_FAILURE"
    assert not owner.is_active(artifact.request_id)
    assert store.state(artifact.activation_authorization_id) == "ABORTED"


def test_app_submit_requires_preissued_activation_authorization(tmp_path):
    _, fake, payload = _ready(tmp_path, RECEIVER, "missing-activation-auth")
    artifact_id = payload["activation_authorization"]["activation_authorization_id"]
    store = app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER._policy.store
    payload["activation_authorization"] = None
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert result["reason"] == "ACTIVATION_AUTHORIZATION_DENIED:ACTIVATION_AUTHORIZATION_MISSING"
    assert fake.calls == 0
    assert store.state(artifact_id) == "ISSUED"


def test_app_configuration_requires_separate_activation_authorization_store(tmp_path):
    store_path, anchor_path = _bootstrap_store(tmp_path)
    registry = ExecutorRegistry()
    registry.register(RECEIVER, FakeQualifiedExecutor(RECEIVER))
    with pytest.raises(
        ValueError, match="MISSING_ESTABLISHED_ACTIVATION_AUTHORIZATION_STORE"
    ):
        app.configure_governed_production_action(
            ProductionAppRuntimeConfig(
                wiring=ProductionWiringConfig(
                    auth_store_path=store_path,
                    auth_anchor_path=anchor_path,
                ),
                clock=ClockCollaborator(now=NOW),
                executor_registry=registry,
                register_real_executors=False,
            )
        )
    assert app._GOVERNED_PRODUCTION_HOST is None


def test_app_authority_failure_occurs_before_activation_authorization_claim(tmp_path):
    _, fake, payload = _ready(tmp_path, RECEIVER, "invalid-authority-first")
    artifact_id = payload["activation_authorization"]["activation_authorization_id"]
    store = app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER._policy.store
    payload["execution_authority"]["artifact_hash"] = "tampered"
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert result["reason"].startswith("EXECUTION_AUTHORITY_INVALID:")
    assert fake.calls == 0
    assert store.state(artifact_id) == "ISSUED"


def test_app_missing_binding_occurs_before_activation_authorization_claim(tmp_path):
    components, fake, payload = _ready(tmp_path, RECEIVER, "missing-binding-first")
    artifact_id = payload["activation_authorization"]["activation_authorization_id"]
    store = app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER._policy.store
    binding = components.composition.binding_controller.get_binding_for_receiver(RECEIVER)
    assert components.composition.binding_controller.teardown(binding)
    result = app.submit_governed_production_action(payload)
    assert result["reason"] == "MISSING_EXPLICIT_BINDING"
    assert fake.calls == 0
    assert store.state(artifact_id) == "ISSUED"


def test_app_happy_path_consumes_and_tears_down_request_activation(tmp_path):
    _, fake, payload = _ready(tmp_path, RECEIVER, "activation-happy")
    artifact_id = payload["activation_authorization"]["activation_authorization_id"]
    store = app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER._policy.store
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    assert fake.calls == 1
    assert store.state(artifact_id) == "CONSUMED"
    events = [e["event_type"] for e in store.events_for_request("activation-happy")]
    assert "ACTIVATION_AUTH_CONSUMED" in events
    assert "PRODUCTION_ACTIVATION_EXITED" in events


def test_explicit_issue_action_does_not_bind_or_execute(tmp_path):
    components, fake, clock = _configure(tmp_path, RECEIVER)
    binding = _bind(components, RECEIVER)
    assert binding.binding_decision == "BOUND"
    _, activation = external_authority_and_activation(RECEIVER, "issue-only", clock=clock)
    spec = QUALIFIED_RECEIVERS[RECEIVER]
    result = app.issue_production_activation_authorization(
        {
            "request_id": "issue-only",
            "receiver_id": RECEIVER,
            "governing_commit": GOVERNING_COMMIT,
            "router_contract_id": activation.router_contract_id,
            "authority_contract_id": activation.authority_contract_id,
            "transport_contract_id": spec["transport_contract_id"],
            "model_binding_id": spec["model_binding_id"],
            "feature_gate_state": "ENABLED",
            "activation_mode": "ENABLED",
            "operator_intent": "EXPLICIT",
            "requested_ttl_seconds": 300,
            "nonce": "activation-auth-issue-only",
        }
    )
    assert result["decision"] == "AUTHORIZED"
    assert (
        components.composition.binding_controller.get_binding_for_receiver(RECEIVER)
        is binding.handle
    )
    assert fake.calls == 0


def test_app_consume_failure_blocks_invocation_and_leaves_recovery_required(
    tmp_path, monkeypatch
):
    components, fake, payload = _ready(tmp_path, RECEIVER, "consume-failure")
    store = app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER._policy.store

    def fail_consume(*_args, **_kwargs):
        raise ProductionActivationAuthorizationStoreError("CONSUME_PERSISTENCE_FAILED")

    monkeypatch.setattr(store, "consume", fail_consume)
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert result["reason"] == "PRODUCTION_ACTIVATION_DENIED:CONSUME_PERSISTENCE_FAILED"
    assert fake.calls == 0
    assert components.composition.binding_controller.active_binding_count == 0
    assert app._GOVERNED_PRODUCTION_RECOVERY._store.has_unresolved()


def test_activation_accounting_order_is_durable(tmp_path):
    _, _, payload = _ready(tmp_path, RECEIVER, "accounting-order")
    store = app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER._policy.store
    assert app.submit_governed_production_action(payload)["decision"] == "ALLOW"
    assert [e["event_type"] for e in store.events_for_request("accounting-order")] == [
        "ACTIVATION_AUTH_REQUESTED",
        "ACTIVATION_AUTH_ISSUED",
        "ACTIVATION_AUTH_CLAIMED",
        "PRODUCTION_ACTIVATION_ENTERED",
        "ACTIVATION_AUTH_CONSUMED",
        "PRODUCTION_ACTIVATION_EXITED",
    ]
