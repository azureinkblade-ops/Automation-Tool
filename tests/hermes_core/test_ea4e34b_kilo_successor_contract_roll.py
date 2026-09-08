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
    "EA-4E.6": "292f7deeb479cd45c6f33f3466305e7f225c05d9f48f9eeb8dc13f944d7162a1",
    "EA-4E.7": "6de9f8b959db33bd2c2885396507baed47a3eadf07423c0e545afe4cc3274661",
    "EA-4E.8": "9785647334992c514ef56013c2e410be48c42a3c1813b377e601823387be67a2",
    "EA-4E.11": "af7d731ff21614f3ab0e92beb8927d3063e06707af7a9a89bc3d3b7c91e7927a",
    "EA-4E.14": "b057272ee70a4f5fceb9500ccf699097ed2de2edfc21e8f47fe3f9247e52f20b",
    "EA-4E.17": "5082b1a227a53cfe711bcf3c5d2193cd47031d75d7ec7650d8ab4c2389194e93",
    "EA-4E.18": "56471e6509ccc2e99a7b609354748c51a0ada18bda8b92648c21bec584c1ceb3",
    "EA-4E.21": "a25a6ba03b6a44f35511bec4b89c332043cd252ea3d1e185bd1b0a5c966fee33",
    "EA-4E.22": "0e9d206a0b5d78592bafad624421439774e6c7ffe34a7c9d4c41a66aeb0504bd",
    "EA-4E.23": "7bc3d2e036beacaef5aaabd054730dfbd49c57a0c36bbaab6f56894798be4687",
    "EA-4E.26": "52edc7ad0be1bf446034ad31189a9172a6a35c98c8619b113f4a836320b8887e",
    "EA-4E.28": "90c96695f6294bed90eed1b630b1b44f7faca859b6b818ea2a744c1b753eb5b1",
    "EA-4E.29": "2d2e42ebbaaa1eacabfbd9a09cf3a542f0424b26c96fb4e6b0a7984245039d87",
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
    assert PINNED_KILO_VERSION == "7.5.15"
    assert PINNED_KILO_PATH.endswith(r"kilocode.kilo-code-7.5.15-win32-x64\bin\kilo.exe")
    assert PINNED_KILO_SHA256 == "78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25"
    assert KILO_TRANSPORT_CONTRACT_ID == "d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd"


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
