"""EA-4E.64A non-live deployment composition qualification, fake only."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

import app
from tools.hermes_core.production_activation_authorization import (
    ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,
    ProductionActivationAuthorizationPolicy,
    ProductionActivationAuthorizationRequest,
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
from tools.hermes_core.production_deployment_composition import (
    DEPLOYMENT_BINDING_SCHEMA_VERSION,
    ProductionDeploymentBindingStore,
    ProductionDeploymentCompositionError,
    ProductionDeploymentCompositionOwner,
    ProductionDeploymentPaths,
)
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingPolicy,
)
from tools.hermes_core.production_issuance import QUALIFIED_RECEIVERS
from tools.hermes_core.receiver_dispatch import compute_ea4e7_authority_contract_id
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


NOW = "2026-09-10T12:00:00+00:00"
GOVERNING_COMMIT = "6096ee0a79299d7ffaa6e8a17860d930c87e3846"
RECEIVER = "kilo-cli-agent"


class FixedClock:
    def __init__(self, now=NOW):
        self.now = datetime.fromisoformat(now)

    def now_iso(self):
        return self.now.isoformat()

    def now_plus_seconds(self, seconds):
        return (self.now + timedelta(seconds=seconds)).isoformat()


class FakeKiloExecutor:
    executor_id = "RealKiloProductionExecutor"

    def __init__(self, counter):
        self.counter = counter

    def execute(self, _request):
        self.counter["calls"] += 1
        raise AssertionError("EA-4E.64A must not execute")


class ReadyPreflight:
    def config_for(self, receiver_id, **values):
        return {"receiver_id": receiver_id, **values}

    def check(self, _config):
        return SimpleNamespace(ready=True, failure_code=None)


@pytest.fixture(autouse=True)
def reset_app_globals(monkeypatch):
    for name in (
        "_GOVERNED_PRODUCTION_COMPONENTS",
        "_GOVERNED_PRODUCTION_HOST",
        "_GOVERNED_PRODUCTION_RECOVERY",
        "_GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER",
        "_GOVERNED_PRODUCTION_DEPLOYMENT_OWNER",
    ):
        monkeypatch.setattr(app, name, None)


def paths(tmp_path):
    return ProductionDeploymentPaths(
        invocation_store_path=tmp_path / "invocation.sqlite3",
        invocation_anchor_path=tmp_path / "invocation.anchor.json",
        activation_store_path=tmp_path / "activation.sqlite3",
        activation_anchor_path=tmp_path / "activation.anchor.json",
        binding_state_path=tmp_path / "binding.sqlite3",
    )


def owner(tmp_path, counter=None, clock=None):
    counter = counter if counter is not None else {"calls": 0}
    return ProductionDeploymentCompositionOwner.provision(
        paths=paths(tmp_path),
        governing_commit=GOVERNING_COMMIT,
        provision_explicit=True,
        clock=clock or FixedClock(),
        credential_preflight=ReadyPreflight(),
        executor_factory=lambda: FakeKiloExecutor(counter),
    )


def policy_for(deployment, clock=None, binding_lookup=None):
    verifier = ProductionOperatorIdentityVerifier(
        ProductionOperatorIdentity("hermes-local-operator")
    )
    return ProductionActivationAuthorizationPolicy(
        store=deployment.activation_store,
        clock=clock or deployment.clock,
        governing_commit=GOVERNING_COMMIT,
        readiness_status="PASS",
        operator_identity_verifier=verifier,
        binding_lookup=(
            binding_lookup
            or deployment.binding_controller.get_binding_for_receiver
        ),
    )


def policy_request(deployment, **changes):
    spec = QUALIFIED_RECEIVERS[RECEIVER]
    store_id, store_epoch = deployment.activation_store.lineage()
    values = dict(
        request_id="ea4e64a-preflight-only",
        receiver_id=RECEIVER,
        governing_commit=GOVERNING_COMMIT,
        router_contract_id=compute_ea4e6_router_contract_id(),
        authority_contract_id=compute_ea4e7_authority_contract_id(),
        transport_contract_id=spec["transport_contract_id"],
        model_binding_id=spec["model_binding_id"],
        feature_gate_state="ENABLED",
        activation_mode="ENABLED",
        operator_intent="EXPLICIT",
        requested_ttl_seconds=300,
        nonce="ea4e64a-preflight-nonce",
        ceremony_id="ea4e64a-preflight-ceremony",
        operator_id="hermes-local-operator",
        activation_store_id=store_id,
        activation_store_epoch=store_epoch,
        executor_binding_id=deployment.binding_handle.binding_id,
        capability_scope=(ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,),
    )
    values.update(changes)
    return ProductionActivationAuthorizationRequest(**values)


def test_explicit_provisioning_is_required(tmp_path):
    with pytest.raises(ProductionDeploymentCompositionError) as exc:
        ProductionDeploymentCompositionOwner.provision(
            paths=paths(tmp_path),
            governing_commit=GOVERNING_COMMIT,
            provision_explicit=False,
        )
    assert exc.value.reason == "EXPLICIT_PROVISIONING_REQUIRED"


def test_provisions_all_stores_and_external_anchors(tmp_path):
    deployment = owner(tmp_path)
    target = paths(tmp_path)
    assert target.invocation_store_path.is_file()
    assert target.invocation_anchor_path.is_file()
    assert target.activation_store_path.is_file()
    assert target.activation_anchor_path.is_file()
    assert target.binding_state_path.is_file()
    assert deployment.activation_store.lineage()[1] == 1
    assert DEPLOYMENT_BINDING_SCHEMA_VERSION == "1"


def test_activation_store_identity_and_epoch_survive_reopen(tmp_path):
    deployment = owner(tmp_path)
    before = deployment.activation_store.lineage()
    reopened = ProductionActivationAuthorizationStore(
        paths(tmp_path).activation_store_path,
        paths(tmp_path).activation_anchor_path,
    )
    assert reopened.lineage() == before


def test_binding_identity_survives_owner_reconstruction(tmp_path):
    counter = {"calls": 0}
    first = owner(tmp_path, counter)
    binding_id = first.binding_handle.binding_id
    second = owner(tmp_path, counter)
    assert second.binding_handle.binding_id == binding_id
    assert second.binding_handle.receiver_id == RECEIVER
    assert counter["calls"] == 0


def test_app_composition_reconstruction_reuses_exact_restored_binding(tmp_path):
    first = owner(tmp_path)
    app.configure_nonlive_production_deployment(first)
    first_id = app._GOVERNED_PRODUCTION_COMPONENTS.composition.binding_controller.get_binding_for_receiver(RECEIVER).binding_id

    second = owner(tmp_path)
    app.configure_nonlive_production_deployment(second)
    second_handle = app._GOVERNED_PRODUCTION_COMPONENTS.composition.binding_controller.get_binding_for_receiver(RECEIVER)
    assert second_handle.binding_id == first_id
    assert app._GOVERNED_PRODUCTION_DEPLOYMENT_OWNER is second


def test_composition_build_issues_no_activation_authorization(tmp_path):
    deployment = owner(tmp_path)
    app.configure_nonlive_production_deployment(deployment)
    assert deployment.activation_store.has_outstanding() is False
    assert app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER is not None
    assert deployment.status()["authorization_issued"] == 0


def test_binding_provision_and_lookup_do_not_execute(tmp_path):
    counter = {"calls": 0}
    deployment = owner(tmp_path, counter)
    assert deployment.binding_controller.get_binding_for_receiver(RECEIVER) is not None
    assert deployment.registry.resolve(RECEIVER) is not None
    assert counter["calls"] == 0


def test_correct_binding_passes_policy_preflight_without_issuance(tmp_path):
    deployment = owner(tmp_path)
    assert policy_for(deployment).evaluate(policy_request(deployment))[0] == "AUTHORIZED"
    assert deployment.activation_store.has_outstanding() is False


def test_wrong_binding_fails_closed(tmp_path):
    deployment = owner(tmp_path)
    request = replace(policy_request(deployment), executor_binding_id="binding-wrong")
    assert policy_for(deployment).evaluate(request)[1] == "EXECUTOR_BINDING_ID_MISMATCH"


def test_missing_binding_fails_closed(tmp_path):
    deployment = owner(tmp_path)
    assert policy_for(deployment, binding_lookup=lambda _receiver: None).evaluate(
        policy_request(deployment)
    )[1] == "EXECUTOR_BINDING_ID_MISSING"


def test_expired_binding_fails_closed(tmp_path):
    deployment = owner(tmp_path)
    later = FixedClock("2026-09-10T14:00:00+00:00")
    assert policy_for(deployment, clock=later).evaluate(policy_request(deployment))[1] == "EXECUTOR_BINDING_EXPIRED"


def test_binding_state_tamper_fails_closed(tmp_path):
    deployment = owner(tmp_path)
    with deployment.binding_store._connect() as connection:
        connection.execute(
            "UPDATE production_executor_binding_state SET payload_json='{}' WHERE singleton=1"
        )
        connection.commit()
    with pytest.raises(ProductionDeploymentCompositionError) as exc:
        ProductionDeploymentBindingStore(paths(tmp_path).binding_state_path).load()
    assert exc.value.reason == "BINDING_STATE_HASH_MISMATCH"


def test_activation_store_replacement_is_refused(tmp_path):
    target = paths(tmp_path)
    owner(tmp_path)
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ProductionActivationAuthStoreBootstrapper().bootstrap(
            target.activation_store_path,
            bootstrap_explicit=True,
            anchor_path=target.activation_anchor_path,
        )
    assert exc.value.reason == "ACTIVATION_AUTH_STORE_ALREADY_EXISTS"


def test_cloned_activation_store_is_not_a_second_valid_domain(tmp_path):
    target = paths(tmp_path)
    owner(tmp_path)
    clone_store = tmp_path / "clone" / "activation.sqlite3"
    clone_anchor = tmp_path / "clone" / "activation.anchor.json"
    clone_store.parent.mkdir()
    shutil.copy2(target.activation_store_path, clone_store)
    shutil.copy2(target.activation_anchor_path, clone_anchor)
    with pytest.raises(ProductionActivationAuthorizationStoreError) as exc:
        ProductionActivationAuthorizationStore(clone_store, clone_anchor)
    assert exc.value.reason == "ACTIVATION_STORE_ANCHOR_MISMATCH"


def test_epoch_rotation_invalidates_prior_authority_domain_without_issuance(tmp_path):
    deployment = owner(tmp_path)
    before = deployment.activation_store.lineage()
    after_epoch = deployment.activation_store.rotate_epoch(
        rotate_explicit=True, now=NOW
    )
    after = deployment.activation_store.lineage()
    assert after[0] == before[0]
    assert after_epoch == after[1] == before[1] + 1
    assert deployment.activation_store.has_outstanding() is False


def test_prohibited_live_counters_remain_zero(tmp_path):
    counter = {"calls": 0}
    deployment = owner(tmp_path, counter)
    app.configure_nonlive_production_deployment(deployment)
    status = deployment.status()
    assert status["authorization_issued"] == 0
    assert status["production_activated"] is False
    assert status["receiver_executed"] is False
    assert status["model_invoked"] is False
    assert counter["calls"] == 0
