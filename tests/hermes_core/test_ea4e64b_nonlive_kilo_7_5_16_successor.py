"""EA-4E.64B non-live Kilo 7.5.16 successor qualification."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.kilo_adapter import (
    KILO_TRANSPORT_CONTRACT_ID,
    PINNED_KILO_PATH,
    PINNED_KILO_SHA256,
    PINNED_KILO_VERSION,
    resolve_pinned_binary,
)
from tools.hermes_core.kilo_successor_binding import (
    HISTORICAL_KILO_7_5_15_EXECUTABLE_BINDING_ID,
    HISTORICAL_KILO_7_5_15_PATH,
    HISTORICAL_KILO_7_5_15_SHA256,
    HISTORICAL_KILO_7_5_15_TRANSPORT_CONTRACT_ID,
    KILO_EXECUTABLE_SUCCESSOR_BINDING_ID,
    KILO_MODEL_BINDING_ID,
    KILO_RECEIVER_ID,
    compute_kilo_executable_successor_binding_id,
    kilo_executable_successor_binding_material,
    verify_kilo_executable_successor_binding,
)
from tools.hermes_core.production_activation_authorization import (
    ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,
    ProductionActivationAuthorizationPolicy,
    ProductionActivationAuthorizationRequest,
)
from tools.hermes_core.production_activation_authorization_ceremony import (
    ProductionOperatorIdentity,
    ProductionOperatorIdentityVerifier,
)
from tools.hermes_core.production_deployment_composition import (
    ProductionDeploymentBindingStore,
    ProductionDeploymentCompositionError,
    ProductionDeploymentCompositionOwner,
    ProductionDeploymentPaths,
)
from tools.hermes_core.production_issuance import QUALIFIED_RECEIVERS
from tools.hermes_core.receiver_dispatch import compute_ea4e7_authority_contract_id
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


NOW = "2026-09-11T12:00:00+00:00"
GOVERNING_COMMIT = "6096ee0a79299d7ffaa6e8a17860d930c87e3846"
EXPECTED_TRANSPORT = "52c828de66703a5ea587e51940dca0ec5c13a92af72b1836e6fc0225a83a5b63"
EXPECTED_EXECUTABLE_BINDING = "f681bc8bbfaeca4b3a1199254583f34327ac0de5e12a3ccbc0ff33411eb96563"


class FixedClock:
    def __init__(self, now: str = NOW) -> None:
        self.now = datetime.fromisoformat(now)

    def now_iso(self) -> str:
        return self.now.isoformat()

    def now_plus_seconds(self, seconds: int) -> str:
        return (self.now + timedelta(seconds=seconds)).isoformat()


class FakeKiloExecutor:
    executor_id = "RealKiloProductionExecutor"

    def __init__(self, counter: dict[str, int]) -> None:
        self.counter = counter

    def execute(self, _request):
        self.counter["calls"] += 1
        raise AssertionError("EA-4E.64B must not execute")


class ReadyPreflight:
    def config_for(self, receiver_id, **values):
        return {"receiver_id": receiver_id, **values}

    def check(self, _config):
        return SimpleNamespace(ready=True, failure_code=None)


def paths(tmp_path: Path) -> ProductionDeploymentPaths:
    return ProductionDeploymentPaths(
        invocation_store_path=tmp_path / "invocation.sqlite3",
        invocation_anchor_path=tmp_path / "invocation.anchor.json",
        activation_store_path=tmp_path / "activation.sqlite3",
        activation_anchor_path=tmp_path / "activation.anchor.json",
        binding_state_path=tmp_path / "binding.sqlite3",
    )


def provision(
    tmp_path: Path,
    counter: dict[str, int],
    *,
    successor_roll_explicit: bool = False,
) -> ProductionDeploymentCompositionOwner:
    return ProductionDeploymentCompositionOwner.provision(
        paths=paths(tmp_path),
        governing_commit=GOVERNING_COMMIT,
        provision_explicit=True,
        successor_roll_explicit=successor_roll_explicit,
        clock=FixedClock(),
        credential_preflight=ReadyPreflight(),
        executor_factory=lambda: FakeKiloExecutor(counter),
    )


def seed_7_5_15_descriptor(deployment: ProductionDeploymentCompositionOwner) -> str:
    payload = deployment.binding_store.load()
    assert payload is not None
    predecessor_id = payload["binding_id"]
    payload.pop("executable_binding_id", None)
    payload["binary_path"] = HISTORICAL_KILO_7_5_15_PATH
    payload["binary_sha256"] = HISTORICAL_KILO_7_5_15_SHA256
    payload["binary_version"] = "7.5.15"
    payload["enablement"]["transport_contract_id"] = (
        HISTORICAL_KILO_7_5_15_TRANSPORT_CONTRACT_ID
    )
    rendered = canonical_json(payload)
    with deployment.binding_store._connect() as connection:
        connection.execute(
            "UPDATE production_executor_binding_state SET payload_json=?, payload_hash=? WHERE singleton=1",
            (rendered, sha256_payload(payload)),
        )
        connection.commit()
    return predecessor_id


def successor_deployment(tmp_path: Path, counter: dict[str, int]):
    first = provision(tmp_path, counter)
    store_lineage = first.activation_store.lineage()
    predecessor_id = seed_7_5_15_descriptor(first)
    successor = provision(tmp_path, counter, successor_roll_explicit=True)
    return successor, predecessor_id, store_lineage


def activation_policy(deployment: ProductionDeploymentCompositionOwner):
    return ProductionActivationAuthorizationPolicy(
        store=deployment.activation_store,
        clock=deployment.clock,
        governing_commit=GOVERNING_COMMIT,
        readiness_status="PASS",
        operator_identity_verifier=ProductionOperatorIdentityVerifier(
            ProductionOperatorIdentity("hermes-local-operator")
        ),
        binding_lookup=deployment.binding_controller.get_binding_for_receiver,
    )


def activation_request(deployment: ProductionDeploymentCompositionOwner, **changes):
    store_id, store_epoch = deployment.activation_store.lineage()
    values = dict(
        request_id="ea4e64b-preflight-only",
        receiver_id=KILO_RECEIVER_ID,
        governing_commit=GOVERNING_COMMIT,
        router_contract_id=compute_ea4e6_router_contract_id(),
        authority_contract_id=compute_ea4e7_authority_contract_id(),
        transport_contract_id=KILO_TRANSPORT_CONTRACT_ID,
        model_binding_id=KILO_MODEL_BINDING_ID,
        feature_gate_state="ENABLED",
        activation_mode="ENABLED",
        operator_intent="EXPLICIT",
        requested_ttl_seconds=300,
        nonce="ea4e64b-preflight-nonce",
        ceremony_id="ea4e64b-preflight-ceremony",
        operator_id="hermes-local-operator",
        activation_store_id=store_id,
        activation_store_epoch=store_epoch,
        executor_binding_id=deployment.binding_handle.binding_id,
        capability_scope=(ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,),
    )
    values.update(changes)
    return ProductionActivationAuthorizationRequest(**values)


def test_installed_binary_identity_is_exact_and_recomputed():
    binary = Path(PINNED_KILO_PATH)
    assert PINNED_KILO_VERSION == "7.5.16"
    assert binary.is_file()
    assert binary.stat().st_size == 170711552
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == PINNED_KILO_SHA256
    assert PINNED_KILO_SHA256 == "8ddb47c7ae088c9f2118cec8824d618eea498b3d580970a5f094c7390633a851"
    identity = resolve_pinned_binary({})
    assert identity.executable == str(binary.resolve())
    assert identity.sha256 == PINNED_KILO_SHA256
    assert identity.version == PINNED_KILO_VERSION


def test_successor_and_predecessor_binary_identities_differ():
    assert PINNED_KILO_SHA256 != HISTORICAL_KILO_7_5_15_SHA256
    assert PINNED_KILO_PATH != HISTORICAL_KILO_7_5_15_PATH


def test_transport_roll_is_exact_and_model_receiver_remain_stable():
    assert KILO_TRANSPORT_CONTRACT_ID == EXPECTED_TRANSPORT
    assert KILO_TRANSPORT_CONTRACT_ID != HISTORICAL_KILO_7_5_15_TRANSPORT_CONTRACT_ID
    assert KILO_MODEL_BINDING_ID == QUALIFIED_RECEIVERS[KILO_RECEIVER_ID]["model_binding_id"]
    assert KILO_RECEIVER_ID == "kilo-cli-agent"


def test_executable_successor_binding_is_exact_and_deterministic():
    assert KILO_EXECUTABLE_SUCCESSOR_BINDING_ID == EXPECTED_EXECUTABLE_BINDING
    assert compute_kilo_executable_successor_binding_id() == EXPECTED_EXECUTABLE_BINDING
    assert KILO_EXECUTABLE_SUCCESSOR_BINDING_ID != HISTORICAL_KILO_7_5_15_EXECUTABLE_BINDING_ID


def test_successor_material_rejects_wrong_binary_hash():
    material = kilo_executable_successor_binding_material()
    assert verify_kilo_executable_successor_binding(material) is True
    assert verify_kilo_executable_successor_binding(
        {**material, "executable_sha256": HISTORICAL_KILO_7_5_15_SHA256}
    ) is False


def test_successor_material_rejects_wrong_executable_binding_inputs():
    material = kilo_executable_successor_binding_material()
    assert verify_kilo_executable_successor_binding(
        {**material, "transport_contract_id": HISTORICAL_KILO_7_5_15_TRANSPORT_CONTRACT_ID}
    ) is False


def test_persisted_predecessor_requires_explicit_successor_roll(tmp_path):
    counter = {"calls": 0}
    first = provision(tmp_path, counter)
    seed_7_5_15_descriptor(first)
    with pytest.raises(ProductionDeploymentCompositionError) as exc:
        provision(tmp_path, counter)
    assert exc.value.reason == "PERSISTED_KILO_BINDING_IDENTITY_MISMATCH"
    assert counter["calls"] == 0


def test_explicit_successor_roll_replaces_old_binding_without_execution(tmp_path):
    counter = {"calls": 0}
    successor, predecessor_id, _ = successor_deployment(tmp_path, counter)
    persisted = successor.binding_store.load()
    assert persisted is not None
    assert successor.binding_handle.binding_id != predecessor_id
    assert persisted["binding_id"] == successor.binding_handle.binding_id
    assert persisted["executable_binding_id"] == EXPECTED_EXECUTABLE_BINDING
    assert persisted["binary_sha256"] == PINNED_KILO_SHA256
    assert persisted["enablement"]["transport_contract_id"] == EXPECTED_TRANSPORT
    assert counter["calls"] == 0


def test_successor_roll_preserves_activation_store_identity_and_epoch(tmp_path):
    counter = {"calls": 0}
    successor, _, prior_lineage = successor_deployment(tmp_path, counter)
    assert successor.activation_store.lineage() == prior_lineage
    assert prior_lineage[1] == 1


def test_successor_binding_survives_reconstruction_with_same_id(tmp_path):
    counter = {"calls": 0}
    successor, _, _ = successor_deployment(tmp_path, counter)
    binding_id = successor.binding_handle.binding_id
    reopened = provision(tmp_path, counter)
    assert reopened.binding_handle.binding_id == binding_id
    assert reopened.binding_store.load()["executable_binding_id"] == EXPECTED_EXECUTABLE_BINDING
    assert counter["calls"] == 0


def test_old_executor_binding_cannot_authorize_successor(tmp_path):
    counter = {"calls": 0}
    successor, predecessor_id, _ = successor_deployment(tmp_path, counter)
    request = replace(
        activation_request(successor), executor_binding_id=predecessor_id
    )
    assert activation_policy(successor).evaluate(request)[1] == "EXECUTOR_BINDING_ID_MISMATCH"
    assert successor.activation_store.has_outstanding() is False


def test_old_transport_cannot_authorize_successor(tmp_path):
    counter = {"calls": 0}
    successor, _, _ = successor_deployment(tmp_path, counter)
    request = replace(
        activation_request(successor),
        transport_contract_id=HISTORICAL_KILO_7_5_15_TRANSPORT_CONTRACT_ID,
    )
    assert activation_policy(successor).evaluate(request)[0] == "DENIED"
    assert successor.activation_store.has_outstanding() is False


def test_wrong_successor_executor_binding_is_denied(tmp_path):
    counter = {"calls": 0}
    successor, _, _ = successor_deployment(tmp_path, counter)
    request = replace(
        activation_request(successor), executor_binding_id="wrong-binding"
    )
    assert activation_policy(successor).evaluate(request)[1] == "EXECUTOR_BINDING_ID_MISMATCH"


def test_binding_store_rejects_wrong_predecessor_identity(tmp_path):
    counter = {"calls": 0}
    deployment = provision(tmp_path, counter)
    payload = deployment.binding_store.load()
    with pytest.raises(ProductionDeploymentCompositionError) as exc:
        deployment.binding_store.replace_successor(
            expected_binding_id="wrong-predecessor", payload=payload
        )
    assert exc.value.reason == "BINDING_STATE_PREDECESSOR_MISMATCH"


def test_missing_qualified_binary_has_no_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tools.hermes_core.kilo_adapter.PINNED_KILO_PATH",
        str(tmp_path / "missing-kilo.exe"),
    )
    with pytest.raises(Exception) as exc:
        resolve_pinned_binary({})
    assert "missing" in str(exc.value).lower() or "not found" in str(exc.value).lower()


def test_successor_composition_closes_prerequisites_without_authorization(tmp_path):
    counter = {"calls": 0}
    successor, _, _ = successor_deployment(tmp_path, counter)
    status = successor.status()
    assert successor.binding_controller.get_binding_for_receiver(KILO_RECEIVER_ID) is not None
    assert successor.activation_store.has_outstanding() is False
    assert status["authorization_issued"] == 0
    assert status["production_activated"] is False
    assert status["receiver_executed"] is False
    assert status["model_invoked"] is False
    assert counter["calls"] == 0


def test_import_and_provisioning_expose_no_automatic_execution(tmp_path):
    counter = {"calls": 0}
    deployment = provision(tmp_path, counter)
    assert deployment.registry.resolve(KILO_RECEIVER_ID) is not None
    assert counter["calls"] == 0
