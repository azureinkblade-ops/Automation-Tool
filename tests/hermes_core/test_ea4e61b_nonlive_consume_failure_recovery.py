"""EA-4E.61B consume-failure recovery remediation. Fake only."""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
import inspect
import sqlite3

import pytest

import app
from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import _ready
from tests.hermes_core.test_ea4e60_nonlive_activation_authorization import (
    RECEIVER,
    _claim,
    _collaborators,
    _issue,
    _request,
)
from tools.hermes_core.production_activation import ProductionActivationValidator
from tools.hermes_core.production_activation_authorization import (
    AUTHORIZED,
    DENIED,
    ProductionActivationAuthorizationValidator,
    ProductionAppActivationTransitionOwner,
)
from tools.hermes_core.production_activation_authorization_store import (
    ProductionActivationAuthorizationStore,
    ProductionActivationAuthorizationStoreError,
)
from tools.hermes_core.production_app_lifecycle import (
    ProductionRequestAdmissionController,
)
from tools.hermes_core.production_app_recovery import (
    ACTIVATION_AUTH_CONSUME_PERSISTENCE_UNCERTAIN,
    ProductionAppRecoveryOwner,
    ProductionRecoveryStore,
)
from tools.hermes_core.production_issuance import QUALIFIED_RECEIVERS
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


@pytest.fixture(autouse=True)
def reset_app_state(monkeypatch):
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_COMPONENTS", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_HOST", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_RECOVERY", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER", None)


class InactiveLiveness:
    def is_host_active(self, _host_instance_id):
        return False

    def inspect_process(self, _process_id, _process_token):
        return "DEAD"


class EmptyBindings:
    def get_binding_for_receiver(self, _receiver_id):
        return None

    def teardown(self, _binding):
        raise AssertionError("recovery must not invent a binding")


class NoProcesses:
    def terminate(self, _process_id, _process_token):
        raise AssertionError("recovery must not start or terminate an absent process")


def _claimed(tmp_path, request_id="request-a", receiver_id=RECEIVER):
    store, clock, policy, issuer = _collaborators(tmp_path)
    request = _request(request_id)
    if receiver_id != RECEIVER:
        spec = QUALIFIED_RECEIVERS[receiver_id]
        request = replace(
            request,
            receiver_id=receiver_id,
            transport_contract_id=spec["transport_contract_id"],
            model_binding_id=spec["model_binding_id"],
        )
    issued = issuer.issue(request)
    assert issued.decision == AUTHORIZED
    claim = policy.claim(
        issued.artifact,
        validator=ProductionActivationAuthorizationValidator(store=store, clock=clock),
        request_id=request_id,
        receiver_id=receiver_id,
        feature_gate_state="ENABLED",
    )
    assert claim.state == "CLAIMED"
    return store, clock, claim


def _recovery(
    tmp_path,
    auth_store,
    clock,
    auth_id,
    *,
    request_id="request-a",
    receiver_id=RECEIVER,
):
    recovery_store = ProductionRecoveryStore.initialize(tmp_path / "recovery.sqlite3")
    admission = ProductionRequestAdmissionController()
    assert admission.acquire(request_id)
    recovery_store.begin(request_id, receiver_id, "stale-host")
    recovery_store.transition(
        request_id,
        "RECOVERY_REQUIRED",
        cleanup_state="PENDING",
        activation_authorization_id=auth_id,
        failure_stage=ACTIVATION_AUTH_CONSUME_PERSISTENCE_UNCERTAIN,
    )
    owner = ProductionAppRecoveryOwner(
        recovery_store,
        admission,
        EmptyBindings(),
        InactiveLiveness(),
        NoProcesses(),
        activation_authorization_store=auth_store,
        activation_clock=clock,
    )
    return recovery_store, owner


def _set_auth_state(store, auth_id, state):
    with closing(sqlite3.connect(str(store.path))) as connection, connection:
        connection.execute(
            "UPDATE production_activation_authorizations SET state=? "
            "WHERE activation_authorization_id=?",
            (state, auth_id),
        )


def test_schema_v1_migrates_to_v2_without_synthesizing_identity(tmp_path):
    path = tmp_path / "legacy-recovery.sqlite3"
    with closing(sqlite3.connect(str(path))) as connection, connection:
        connection.execute(
            "CREATE TABLE recovery_schema_version "
            "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL)"
        )
        connection.execute("INSERT INTO recovery_schema_version VALUES(1, 1)")
        connection.execute(
            """CREATE TABLE production_recovery_state (
            request_id TEXT PRIMARY KEY, receiver_id TEXT NOT NULL,
            host_instance_id TEXT NOT NULL, admission_owner_id TEXT NOT NULL,
            binding_id TEXT, enablement_id TEXT, invocation_authorization_id TEXT,
            process_id TEXT, process_token TEXT, process_state TEXT NOT NULL,
            lifecycle_phase TEXT NOT NULL, cleanup_state TEXT NOT NULL)"""
        )
        connection.execute(
            "INSERT INTO production_recovery_state VALUES "
            "('legacy', 'kilo-cli-agent', 'host', 'legacy', NULL, NULL, NULL, "
            "NULL, NULL, 'NOT_REGISTERED', 'RECOVERY_REQUIRED', 'PENDING')"
        )

    store = ProductionRecoveryStore.initialize(path)
    record = store.load("legacy")
    assert record is not None
    assert record.activation_authorization_id is None
    assert record.failure_stage is None
    with closing(sqlite3.connect(str(path))) as connection:
        assert connection.execute(
            "SELECT version FROM recovery_schema_version WHERE singleton=1"
        ).fetchone()[0] == 2


def test_consume_failure_marker_records_exact_identity_and_stage(tmp_path, monkeypatch):
    store, clock, claim = _claimed(tmp_path)
    _, activation = external_authority_and_activation(
        RECEIVER, claim.artifact.request_id, clock=clock
    )
    recorded = []
    owner = ProductionAppActivationTransitionOwner(
        store=store,
        clock=clock,
        activation_validator=ProductionActivationValidator(
            router_contract_id=compute_ea4e6_router_contract_id()
        ),
        consume_failure_recovery_marker=lambda *args: recorded.append(args),
    )
    monkeypatch.setattr(
        store,
        "consume",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProductionActivationAuthorizationStoreError("CONSUME_PERSISTENCE_FAILED")
        ),
    )
    result = owner.transition(
        request_id=claim.artifact.request_id,
        receiver_id=RECEIVER,
        claimed_authorization=claim,
        production_activation=activation,
    )
    assert result.decision == DENIED
    assert result.recovery_required
    assert recorded == [
        (
            claim.artifact.request_id,
            claim.artifact.activation_authorization_id,
            ACTIVATION_AUTH_CONSUME_PERSISTENCE_UNCERTAIN,
        )
    ]
    assert not owner.is_active(claim.artifact.request_id)


def test_double_write_failure_is_denied_and_activation_is_disabled(tmp_path, monkeypatch):
    store, clock, claim = _claimed(tmp_path)
    _, activation = external_authority_and_activation(
        RECEIVER, claim.artifact.request_id, clock=clock
    )
    owner = ProductionAppActivationTransitionOwner(
        store=store,
        clock=clock,
        activation_validator=ProductionActivationValidator(
            router_contract_id=compute_ea4e6_router_contract_id()
        ),
        consume_failure_recovery_marker=lambda *_args: (_ for _ in ()).throw(
            RuntimeError("RECOVERY_WRITE_FAILED")
        ),
    )
    monkeypatch.setattr(
        store,
        "consume",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProductionActivationAuthorizationStoreError("CONSUME_PERSISTENCE_FAILED")
        ),
    )
    result = owner.transition(
        request_id=claim.artifact.request_id,
        receiver_id=RECEIVER,
        claimed_authorization=claim,
        production_activation=activation,
    )
    assert result.decision == DENIED
    assert result.reason == "CONSUME_PERSISTENCE_AND_RECOVERY_MARKER_FAILED"
    assert result.recovery_required
    assert not owner.is_active(claim.artifact.request_id)
    assert store.state(claim.artifact.activation_authorization_id) == "CLAIMED"


def test_claimed_recovery_aborts_once_and_survives_reopen(tmp_path):
    auth_store, clock, claim = _claimed(tmp_path)
    recovery_store, owner = _recovery(
        tmp_path, auth_store, clock, claim.artifact.activation_authorization_id
    )
    reopened = ProductionRecoveryStore(recovery_store.path)
    assert reopened.load("request-a").activation_authorization_id == (
        claim.artifact.activation_authorization_id
    )

    first = owner.reconcile("request-a")
    event_count = len(auth_store.events_for_request("request-a"))
    second = owner.reconcile("request-a")
    assert (first.decision, first.reason) == ("ALLOW", "RECOVERED")
    assert (second.decision, second.reason) == ("ALLOW", "ALREADY_CLEAN")
    assert auth_store.state(claim.artifact.activation_authorization_id) == "ABORTED"
    assert len(auth_store.events_for_request("request-a")) == event_count
    assert recovery_store.load("request-a").cleanup_state == "CLEAN"


@pytest.mark.parametrize(
    ("terminal_state", "expected"),
    [("CONSUMED", "CONSUMED"), ("ABORTED", "ABORTED")],
)
def test_terminal_recovery_state_is_preserved_without_rewrite(
    tmp_path, terminal_state, expected
):
    auth_store, clock, claim = _claimed(tmp_path)
    if terminal_state == "CONSUMED":
        auth_store.consume(claim.artifact.activation_authorization_id, clock.now_iso())
    else:
        auth_store.abort(claim.artifact.activation_authorization_id, clock.now_iso())
    recovery_store, owner = _recovery(
        tmp_path, auth_store, clock, claim.artifact.activation_authorization_id
    )
    event_count = len(auth_store.events_for_request("request-a"))
    assert owner.reconcile("request-a").decision == "ALLOW"
    assert auth_store.state(claim.artifact.activation_authorization_id) == expected
    assert len(auth_store.events_for_request("request-a")) == event_count
    assert recovery_store.load("request-a").cleanup_state == "CLEAN"


@pytest.mark.parametrize("invalid_state", ["ISSUED", "DENIED", "EXPIRED"])
def test_impossible_recovery_source_states_are_denied(tmp_path, invalid_state):
    if invalid_state == "ISSUED":
        auth_store, clock, _, artifact = _issue(tmp_path)
    else:
        auth_store, clock, claim = _claimed(tmp_path)
        artifact = claim.artifact
        _set_auth_state(auth_store, artifact.activation_authorization_id, invalid_state)
    recovery_store, owner = _recovery(
        tmp_path, auth_store, clock, artifact.activation_authorization_id
    )
    assert owner.reconcile("request-a").decision == "DENY"
    assert auth_store.state(artifact.activation_authorization_id) == invalid_state
    assert recovery_store.load("request-a").cleanup_state == "FAILED"


def test_unknown_authorization_id_is_denied_without_fallback(tmp_path):
    auth_store, clock, _ = _claimed(tmp_path)
    recovery_store, owner = _recovery(tmp_path, auth_store, clock, "unknown-auth")
    assert owner.reconcile("request-a").decision == "DENY"
    assert recovery_store.load("request-a").cleanup_state == "FAILED"


@pytest.mark.parametrize(
    ("request_id", "receiver_id"),
    [("different-request", RECEIVER), ("request-a", "opencode-cli-agent")],
)
def test_recovery_identity_mismatch_is_denied(tmp_path, request_id, receiver_id):
    auth_store, clock, claim = _claimed(tmp_path)
    recovery_store, owner = _recovery(
        tmp_path,
        auth_store,
        clock,
        claim.artifact.activation_authorization_id,
        request_id=request_id,
        receiver_id=receiver_id,
    )
    assert owner.reconcile(request_id).decision == "DENY"
    assert auth_store.state(claim.artifact.activation_authorization_id) == "CLAIMED"
    assert recovery_store.load(request_id).cleanup_state == "FAILED"


def test_malformed_authorization_row_is_denied_without_repair(tmp_path):
    auth_store, clock, claim = _claimed(tmp_path)
    with closing(sqlite3.connect(str(auth_store.path))) as connection, connection:
        connection.execute(
            "UPDATE production_activation_authorizations SET artifact_json='{}' "
            "WHERE activation_authorization_id=?",
            (claim.artifact.activation_authorization_id,),
        )
    recovery_store, owner = _recovery(
        tmp_path, auth_store, clock, claim.artifact.activation_authorization_id
    )
    assert owner.reconcile("request-a").decision == "DENY"
    assert auth_store.state(claim.artifact.activation_authorization_id) == "CLAIMED"
    assert recovery_store.load("request-a").cleanup_state == "FAILED"


def test_legacy_recovery_row_without_auth_identity_fails_closed(tmp_path):
    auth_store, clock, _ = _claimed(tmp_path)
    recovery_store = ProductionRecoveryStore.initialize(tmp_path / "recovery.sqlite3")
    admission = ProductionRequestAdmissionController()
    assert admission.acquire("request-a")
    recovery_store.begin("request-a", RECEIVER, "stale-host")
    recovery_store.transition(
        "request-a",
        "RECOVERY_REQUIRED",
        cleanup_state="PENDING",
        failure_stage=ACTIVATION_AUTH_CONSUME_PERSISTENCE_UNCERTAIN,
    )
    owner = ProductionAppRecoveryOwner(
        recovery_store,
        admission,
        EmptyBindings(),
        InactiveLiveness(),
        NoProcesses(),
        activation_authorization_store=auth_store,
        activation_clock=clock,
    )
    assert owner.reconcile("request-a").decision == "DENY"


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_fake_app_consume_failure_records_identity_and_never_executes(
    tmp_path, monkeypatch, receiver_id
):
    components, fake, payload = _ready(tmp_path, receiver_id, f"consume-{receiver_id}")
    auth_store = app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER._policy.store
    auth_id = payload["activation_authorization"]["activation_authorization_id"]
    monkeypatch.setattr(
        auth_store,
        "consume",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProductionActivationAuthorizationStoreError("CONSUME_PERSISTENCE_FAILED")
        ),
    )
    result = app.submit_governed_production_action(payload)
    record = app._GOVERNED_PRODUCTION_RECOVERY._store.load(payload["request_id"])
    assert result["decision"] == "DENY"
    assert fake.calls == 0
    assert components.composition.binding_controller.active_binding_count == 0
    assert record.activation_authorization_id == auth_id
    assert record.failure_stage == ACTIVATION_AUTH_CONSUME_PERSISTENCE_UNCERTAIN
    assert auth_store.state(auth_id) == "CLAIMED"


def test_normal_consume_and_transition_failure_paths_remain_unchanged(tmp_path):
    store, clock, policy, artifact = _issue(tmp_path, "normal")
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
    assert owner.transition(
        request_id=artifact.request_id,
        receiver_id=RECEIVER,
        claimed_authorization=claim,
        production_activation=activation,
    ).durable_authorization_state == "CONSUMED"

    store2, clock2, policy2, artifact2 = _issue(tmp_path / "invalid", "invalid")
    claim2 = _claim(store2, clock2, policy2, artifact2)
    owner2 = ProductionAppActivationTransitionOwner(
        store=store2,
        clock=clock2,
        activation_validator=ProductionActivationValidator(
            router_contract_id=compute_ea4e6_router_contract_id()
        ),
    )
    assert owner2.transition(
        request_id=artifact2.request_id,
        receiver_id=RECEIVER,
        claimed_authorization=claim2,
        production_activation=None,
    ).durable_authorization_state == "ABORTED"


def test_grok_remains_denied_without_issuance(tmp_path):
    store, _, _, issuer = _collaborators(tmp_path)
    result = issuer.issue(_request(receiver_id="grok-agent"))
    assert result.decision == DENIED
    assert result.reason == "UNSUPPORTED_RECEIVER"
    assert not store.has_outstanding()


def test_recovery_surface_has_no_authorize_bind_or_execute_capability():
    source = inspect.getsource(ProductionAppRecoveryOwner)
    assert "ProductionActivationAuthorizationIssuer" not in source
    assert "issue_production_activation_authorization" not in source
    assert ".bind(" not in source
    assert ".submit(" not in source
    assert "subprocess" not in source
    assert "ComfyUI" not in source


def test_reopen_does_not_implicitly_recover_or_activate(tmp_path):
    auth_store, clock, claim = _claimed(tmp_path)
    recovery_store, _ = _recovery(
        tmp_path, auth_store, clock, claim.artifact.activation_authorization_id
    )
    reopened_recovery = ProductionRecoveryStore(recovery_store.path)
    reopened_auth = ProductionActivationAuthorizationStore(auth_store.path)
    assert reopened_recovery.has_unresolved()
    assert reopened_recovery.load("request-a").cleanup_state == "PENDING"
    assert reopened_auth.state(claim.artifact.activation_authorization_id) == "CLAIMED"
