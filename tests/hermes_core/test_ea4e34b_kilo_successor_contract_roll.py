"""EA-4E.34B Kilo 7.5.15 successor-chain qualification."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from tools.hermes_core.governed_bound_executor import compute_ea4e22_integration_contract_id
from tools.hermes_core.governed_production import compute_ea4e18_integration_contract_id
from tools.hermes_core.governed_production_caller import compute_ea4e29_caller_contract_id
from tools.hermes_core.governed_production_runtime import compute_ea4e26_integration_contract_id
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.kilo_adapter import (
    KILO_TRANSPORT_CONTRACT_ID,
    PINNED_KILO_PATH,
    PINNED_KILO_SHA256,
    PINNED_KILO_VERSION,
    _canonical_material,
)
from tools.hermes_core.kilo_successor_binding import (
    CURRENT_EA4E17_ISSUANCE_CONTRACT_ID,
    CURRENT_EA4E21_BINDING_CONTRACT_ID,
    CURRENT_EA4E22_INTEGRATION_CONTRACT_ID,
    HISTORICAL_EA4E_CONTRACT_IDS,
    HISTORICAL_EA4E_7_5_15_CONTRACT_IDS,
    HISTORICAL_KILO_7_5_15_EXECUTABLE_BINDING_ID,
    HISTORICAL_KILO_7_5_15_TRANSPORT_CONTRACT_ID,
    HISTORICAL_KILO_7_5_9_TRANSPORT_CONTRACT_ID,
    KILO_EXECUTABLE_SUCCESSOR_BINDING_ID,
    KILO_MODEL_BINDING_ID,
    compute_historical_kilo_7_5_9_transport_contract_id,
    compute_kilo_executable_successor_binding_id,
    kilo_executable_successor_binding_material,
    verify_kilo_executable_successor_binding,
)
from tools.hermes_core.production_activation import compute_ea4e11_activation_contract_id
from tools.hermes_core.production_dispatch import compute_ea4e8_coordinator_contract_id
from tools.hermes_core.production_execution import compute_ea4e14_execution_contract_id
from tools.hermes_core.production_executor_binding import (
    ALLOWED_DELEGATION_CLASS,
    ALLOWED_RUNTIME_SCOPE,
    MAX_SIMULTANEOUS_REAL_BINDINGS,
    BindingClock,
    ProductionExecutorBindingEnablement,
    ProductionExecutorBindingPolicy,
    compute_ea4e21_binding_contract_id,
)
from tools.hermes_core.production_invocation_authorization import (
    AUTHORIZATION_STORE_SCHEMA_VERSION,
    compute_ea4e23_invocation_contract_id,
)
from tools.hermes_core.production_invocation_authorization_issuer import compute_ea4e28_issuer_contract_id
from tools.hermes_core.production_issuance import compute_ea4e17_issuance_contract_id
from tools.hermes_core.receiver_dispatch import compute_ea4e7_authority_contract_id
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthorityScope,
    ExecutionAuthorityValidator,
    build_dispatch_authority,
)
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    ReceiverRouter,
    RoutingRequest,
    compute_ea4e6_router_contract_id,
)


EXPECTED_IDS = {
    "EA-4E.6": "a80122e6363f67148f9737f096057f2874aa594f04ddb2d18ddab3598fa94c49",
    "EA-4E.7": "05cad9f532b0bc37a5fa28104f72b14a08b53d050c37912f6e367edb22cadfe4",
    "EA-4E.8": "57b48875a3d446e4c2a417975c235c7360d4be6c96b4f0e380965553a126402d",
    "EA-4E.11": "578e0790c6317298d7c81ab5b0ed58e46a197aecdece050ed59c18d9ef29d2d0",
    "EA-4E.14": "ef709f6c2678027f694c3c9a55a498ec973977868428116bfa8b9476118f7f52",
    "EA-4E.17": "62ba7ba5689ff467b8609f924abdf6f1d478a037214dd99c4cbdcccbf6dfbd5b",
    "EA-4E.18": "921ea6c7ce32e57880bd67116e18f943faa66d265f685a9b59d632123c371cb3",
    "EA-4E.21": "eac6a628e11d3d7235e09a2bf745bc2efda9856baf47c432b7ad4813a36691de",
    "EA-4E.22": "93b284477a6f760170058a6ed026592d2238f0a1da7b5905eab8f70c6316eefe",
    "EA-4E.23": "b918118df4b7d72ab632737ce75ca700426e40932cd21a83ead15b3d20ee2319",
    "EA-4E.26": "05880849e3972a5553c2ea7b9ed7e75df33bc8ca3f990df9bf65bc9b15da9891",
    "EA-4E.28": "4b1953dbdf28753a940bb6fed41ea38efd7ed92d657e9d3cdca4b1b760105c88",
    "EA-4E.29": "ac2c38e726a2469b80590f6976acad9a5141e0efb26c2726e342420118ef21f1",
}


def _current_ids() -> dict[str, str]:
    return {
        "EA-4E.6": compute_ea4e6_router_contract_id(),
        "EA-4E.7": compute_ea4e7_authority_contract_id(),
        "EA-4E.8": compute_ea4e8_coordinator_contract_id(),
        "EA-4E.11": compute_ea4e11_activation_contract_id(),
        "EA-4E.14": compute_ea4e14_execution_contract_id(),
        "EA-4E.17": compute_ea4e17_issuance_contract_id(),
        "EA-4E.18": compute_ea4e18_integration_contract_id(),
        "EA-4E.21": compute_ea4e21_binding_contract_id(),
        "EA-4E.22": compute_ea4e22_integration_contract_id(),
        "EA-4E.23": compute_ea4e23_invocation_contract_id(),
        "EA-4E.26": compute_ea4e26_integration_contract_id(),
        "EA-4E.28": compute_ea4e28_issuer_contract_id(),
        "EA-4E.29": compute_ea4e29_caller_contract_id(),
    }


def _valid_enablement() -> ProductionExecutorBindingEnablement:
    return ProductionExecutorBindingEnablement(
        enablement_id="ea4e34b-enablement",
        receiver_id="kilo-cli-agent",
        transport_contract_id=KILO_TRANSPORT_CONTRACT_ID,
        model_binding_id=KILO_MODEL_BINDING_ID,
        executor_identity="RealKiloProductionExecutor",
        executor_factory="tools.hermes_core.kilo_live_binding:RealKiloProductionExecutor",
        runtime_scope=ALLOWED_RUNTIME_SCOPE,
        delegation_class=ALLOWED_DELEGATION_CLASS,
        requested_ttl_seconds=Decimal("3600"),
        max_bound_executors=MAX_SIMULTANEOUS_REAL_BINDINGS,
        enabled=True,
        request_nonce="ea4e34b-nonce",
        issued_at="2025-12-31T23:30:00+00:00",
        expires_at="2026-01-01T00:30:00+00:00",
    )


def test_successor_file_identity_and_transport_are_exact():
    assert PINNED_KILO_VERSION == "7.5.16"
    assert PINNED_KILO_PATH.endswith(r"kilocode.kilo-code-7.5.16-win32-x64\bin\kilo.exe")
    assert PINNED_KILO_SHA256 == "8ddb47c7ae088c9f2118cec8824d618eea498b3d580970a5f094c7390633a851"
    assert KILO_TRANSPORT_CONTRACT_ID == "52c828de66703a5ea587e51940dca0ec5c13a92af72b1836e6fc0225a83a5b63"


def test_transport_and_binding_hashes_are_deterministic_and_order_invariant():
    material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
    assert sha256_payload(material) == KILO_TRANSPORT_CONTRACT_ID
    assert sha256_payload(dict(reversed(list(material.items())))) == KILO_TRANSPORT_CONTRACT_ID
    assert compute_kilo_executable_successor_binding_id() == KILO_EXECUTABLE_SUCCESSOR_BINDING_ID
    assert sha256_payload(dict(reversed(list(kilo_executable_successor_binding_material().items())))) == KILO_EXECUTABLE_SUCCESSOR_BINDING_ID


def test_old_transport_and_chain_ids_remain_historical_and_reproducible():
    assert compute_historical_kilo_7_5_9_transport_contract_id() == HISTORICAL_KILO_7_5_9_TRANSPORT_CONTRACT_ID
    assert set(HISTORICAL_EA4E_CONTRACT_IDS) == set(EXPECTED_IDS)
    assert all(HISTORICAL_EA4E_CONTRACT_IDS[key] != EXPECTED_IDS[key] for key in EXPECTED_IDS)
    assert set(HISTORICAL_EA4E_7_5_15_CONTRACT_IDS) == set(EXPECTED_IDS)
    assert all(HISTORICAL_EA4E_7_5_15_CONTRACT_IDS[key] != EXPECTED_IDS[key] for key in EXPECTED_IDS)
    assert HISTORICAL_KILO_7_5_15_TRANSPORT_CONTRACT_ID != KILO_TRANSPORT_CONTRACT_ID
    assert HISTORICAL_KILO_7_5_15_EXECUTABLE_BINDING_ID != KILO_EXECUTABLE_SUCCESSOR_BINDING_ID


def test_rolled_chain_matches_exact_ids_and_is_repeatable():
    assert _current_ids() == EXPECTED_IDS
    assert _current_ids() == EXPECTED_IDS
    assert CURRENT_EA4E17_ISSUANCE_CONTRACT_ID == EXPECTED_IDS["EA-4E.17"]
    assert CURRENT_EA4E21_BINDING_CONTRACT_ID == EXPECTED_IDS["EA-4E.21"]
    assert CURRENT_EA4E22_INTEGRATION_CONTRACT_ID == EXPECTED_IDS["EA-4E.22"]


def test_receiver_set_model_and_opencode_bindings_are_unchanged():
    assert set(QUALIFIED_RECEIVERS) == {"opencode-cli-agent", "kilo-cli-agent"}
    assert QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"] == KILO_MODEL_BINDING_ID
    assert QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"] == "192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f"
    assert QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"] == "cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371"
    assert AUTHORIZATION_STORE_SCHEMA_VERSION == "1"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"transport_contract_id": HISTORICAL_KILO_7_5_9_TRANSPORT_CONTRACT_ID}, "TRANSPORT_CONTRACT_MISMATCH"),
        ({"transport_contract_id": QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"]}, "TRANSPORT_CONTRACT_MISMATCH"),
        ({"model_binding_id": "wrong-model"}, "MODEL_BINDING_MISMATCH"),
        ({"model_binding_id": QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"]}, "MODEL_BINDING_MISMATCH"),
        ({"receiver_id": "kilo-7.5.15"}, "UNSUPPORTED_RECEIVER"),
        ({"executor_identity": "RealOpenCodeProductionExecutor"}, "EXECUTOR_IDENTITY_MISMATCH"),
        ({"executor_factory": "wrong.factory"}, "EXECUTOR_FACTORY_MISMATCH"),
        ({"runtime_scope": "development"}, "UNSUPPORTED_RUNTIME_SCOPE"),
        ({"delegation_class": "ambient"}, "DELEGATION_CLASS_MISMATCH"),
        ({"enabled": False}, "ENABLEMENT_NOT_ENABLED"),
    ],
)
def test_successor_mismatch_matrix_fails_closed(changes, reason):
    policy = ProductionExecutorBindingPolicy(
        clock=BindingClock(now="2026-01-01T00:00:00+00:00")
    )
    result = policy.evaluate(replace(_valid_enablement(), **changes))
    assert result.policy_decision == "REJECT"
    assert result.binding_authorized is False
    assert result.policy_reason == reason


def test_old_and_malformed_successor_bindings_are_not_substituted():
    current = kilo_executable_successor_binding_material()
    assert verify_kilo_executable_successor_binding(current)
    old = dict(current, executable_version="7.5.9", transport_contract_id=HISTORICAL_KILO_7_5_9_TRANSPORT_CONTRACT_ID)
    missing = dict(current)
    missing.pop("executable_sha256")
    assert not verify_kilo_executable_successor_binding(old)
    assert not verify_kilo_executable_successor_binding(missing)


def test_required_old_new_and_cross_receiver_mismatch_matrix_fails_closed():
    current_router = ReceiverRouter()
    current_route = current_router.route(RoutingRequest(
        receiver_id="kilo-cli-agent", execution_authority_present=True
    ))
    old_receivers = {key: dict(value) for key, value in QUALIFIED_RECEIVERS.items()}
    old_receivers["kilo-cli-agent"]["transport_contract_id"] = (
        HISTORICAL_KILO_7_5_9_TRANSPORT_CONTRACT_ID
    )
    old_router = ReceiverRouter(qualified_receivers=old_receivers)
    old_route = old_router.route(RoutingRequest(
        receiver_id="kilo-cli-agent", execution_authority_present=True
    ))

    def authority(receiver_id, transport, model, router_id):
        return build_dispatch_authority(
            receiver_id=receiver_id,
            transport_contract_id=transport,
            model_binding_id=model,
            router_contract_id=router_id,
            scope=DispatchAuthorityScope(
                operation="receiver-dispatch", receiver_id=receiver_id
            ),
            delegation_class="governed",
            decision="GRANTED",
            issued_at="2026-01-01T00:00:00Z",
            expires_at="2099-01-01T00:00:00Z",
            nonce="ea4e34c-mismatch",
        )

    current_validator = ExecutionAuthorityValidator(
        router_contract_id=current_router.get_contract_id(),
        qualified_receivers=QUALIFIED_RECEIVERS,
    )
    old_validator = ExecutionAuthorityValidator(
        router_contract_id=old_router.get_contract_id(),
        qualified_receivers=old_receivers,
    )

    outcomes = {
        "old_transport_new_chain": current_validator.validate(
            authority("kilo-cli-agent", HISTORICAL_KILO_7_5_9_TRANSPORT_CONTRACT_ID, KILO_MODEL_BINDING_ID, current_router.get_contract_id()),
            current_route,
        ).dispatch_decision,
        "new_transport_old_chain": old_validator.validate(
            authority("kilo-cli-agent", KILO_TRANSPORT_CONTRACT_ID, KILO_MODEL_BINDING_ID, old_router.get_contract_id()),
            old_route,
        ).dispatch_decision,
        "old_binding_new_chain": "REJECT" if not verify_kilo_executable_successor_binding(
            dict(kilo_executable_successor_binding_material(), executable_version="7.5.9", transport_contract_id=HISTORICAL_KILO_7_5_9_TRANSPORT_CONTRACT_ID)
        ) else "ALLOW",
        "new_binding_old_chain": "REJECT" if kilo_executable_successor_binding_material()["transport_contract_id"] != HISTORICAL_KILO_7_5_9_TRANSPORT_CONTRACT_ID else "ALLOW",
        "opencode_transport_for_kilo": current_validator.validate(
            authority("kilo-cli-agent", QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"], KILO_MODEL_BINDING_ID, current_router.get_contract_id()),
            current_route,
        ).dispatch_decision,
        "kilo_transport_for_opencode": current_validator.validate(
            authority("opencode-cli-agent", KILO_TRANSPORT_CONTRACT_ID, QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"], current_router.get_contract_id()),
            current_router.route(RoutingRequest(receiver_id="opencode-cli-agent", execution_authority_present=True)),
        ).dispatch_decision,
        "wrong_model": current_validator.validate(
            authority("kilo-cli-agent", KILO_TRANSPORT_CONTRACT_ID, "wrong-model", current_router.get_contract_id()),
            current_route,
        ).dispatch_decision,
        "wrong_receiver": current_router.route(RoutingRequest(
            receiver_id="kilo-7.5.15", execution_authority_present=True
        )).route_decision,
        "wrong_router": current_validator.validate(
            authority("kilo-cli-agent", KILO_TRANSPORT_CONTRACT_ID, KILO_MODEL_BINDING_ID, "wrong-router"),
            current_route,
        ).dispatch_decision,
        "malformed_successor_binding": "REJECT" if not verify_kilo_executable_successor_binding(
            {"receiver_id": "kilo-cli-agent"}
        ) else "ALLOW",
    }
    assert len(outcomes) == 10
    assert set(outcomes.values()) == {"REJECT"}
