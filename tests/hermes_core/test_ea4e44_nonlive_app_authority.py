"""EA-4E.44 non-live app-facing execution-authority collaborator. Fake only."""

from __future__ import annotations

import pytest

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_app_authority import (
    ProductionAppAuthorityCollaborator,
    ProductionAppAuthorityRequest,
)
from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_issuance import ClockCollaborator, ProductionIssuancePolicy
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    RoutingResult,
    compute_ea4e6_router_contract_id,
)


NOW = "2026-01-01T00:00:00Z"
TRIPWIRE_HITS = {
    "executor": 0,
    "adapter": 0,
    "process": 0,
    "model": 0,
    "invocation": 0,
    "store_init": 0,
    "binding": 0,
}


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(
        executor=0, adapter=0, process=0, model=0, invocation=0, store_init=0, binding=0
    )

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E44_REAL_{category.upper()}_TRIPWIRE")

        return reject

    monkeypatch.setattr(RealKiloProductionExecutor, "execute", trip("executor"))
    monkeypatch.setattr(RealOpenCodeProductionExecutor, "execute", trip("executor"))
    monkeypatch.setattr(KiloAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(KiloProcessController, "start", trip("process"))
    monkeypatch.setattr(OpenCodeLiveProcess, "start", trip("process"))
    monkeypatch.setattr(ProductionInvocationAuthorizationIssuer, "issue", trip("invocation"))
    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", trip("store_init"))
    monkeypatch.setattr(ProductionExecutorBindingController, "bind", trip("binding"))
    yield TRIPWIRE_HITS
    assert TRIPWIRE_HITS["executor"] == 0
    assert TRIPWIRE_HITS["adapter"] == 0
    assert TRIPWIRE_HITS["process"] == 0
    assert TRIPWIRE_HITS["model"] == 0
    assert TRIPWIRE_HITS["invocation"] == 0
    assert TRIPWIRE_HITS["store_init"] == 0
    assert TRIPWIRE_HITS["binding"] == 0


def collaborator():
    return ProductionAppAuthorityCollaborator(
        ProductionIssuancePolicy(clock=ClockCollaborator(now=NOW))
    )


def route(receiver_id, decision="SELECTED"):
    return RoutingResult(
        receiver_id=receiver_id,
        qualification_state="QUALIFIED",
        route_decision=decision,
        route_reason="explicit",
        execution_authority_present=True,
    )


def req(receiver_id="kilo-cli-agent", request_id="ea4e44-a", **changes):
    fields = {
        "execution_request_id": request_id,
        "receiver_id": receiver_id,
        "transport_contract_id": QUALIFIED_RECEIVERS[receiver_id]["transport_contract_id"]
        if receiver_id in QUALIFIED_RECEIVERS
        else "x",
        "model_binding_id": QUALIFIED_RECEIVERS[receiver_id]["model_binding_id"]
        if receiver_id in QUALIFIED_RECEIVERS
        else "y",
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "delegation_class": "governed",
        "requested_operation": "receiver-dispatch",
        "requested_execution_scope": "production",
        "requested_attempt_limit": 1,
        "requested_authority_ttl_seconds": 300,
        "request_nonce": f"nonce-{request_id}",
        "routing_result": route(receiver_id) if receiver_id else None,
    }
    fields.update(changes)
    return ProductionAppAuthorityRequest(**fields)


def test_missing_request():
    result = collaborator().issue(None)
    assert result.authority_reason == "MISSING_REQUEST"


def test_missing_execution_request_id():
    result = collaborator().issue(req(request_id=""))
    assert result.authority_reason == "MISSING_EXECUTION_REQUEST_ID"


def test_missing_receiver():
    result = collaborator().issue(req(receiver_id=None, routing_result=None))
    assert result.authority_reason == "MISSING_RECEIVER"


def test_unsupported_receiver():
    result = collaborator().issue(
        req(receiver_id="codex-cli-agent", routing_result=route("codex-cli-agent"))
    )
    assert result.authority_reason == "UNSUPPORTED_RECEIVER"


def test_grok_receiver():
    result = collaborator().issue(req(receiver_id="grok", routing_result=route("grok")))
    assert result.authority_reason == "UNSUPPORTED_RECEIVER"


def test_missing_transport_id():
    result = collaborator().issue(req(transport_contract_id=""))
    assert result.authority_reason == "MISSING_TRANSPORT_ID"


def test_missing_model_binding_id():
    result = collaborator().issue(req(model_binding_id=""))
    assert result.authority_reason == "MISSING_MODEL_BINDING_ID"


def test_missing_router_contract_id():
    result = collaborator().issue(req(router_contract_id=""))
    assert result.authority_reason == "MISSING_ROUTER_CONTRACT_ID"


def test_invalid_scope():
    result = collaborator().issue(req(requested_execution_scope="lab"))
    assert result.authority_decision == "DENY"
    assert result.authority_reason == "EXECUTION_SCOPE_MISMATCH"


def test_invalid_delegation_class():
    result = collaborator().issue(req(delegation_class="ungoverned"))
    assert result.authority_reason == "DELEGATION_CLASS_MISMATCH"


def test_missing_nonce():
    result = collaborator().issue(req(request_nonce=""))
    assert result.authority_reason == "MISSING_NONCE"


def test_invalid_expiry():
    result = collaborator().issue(req(requested_authority_ttl_seconds=0))
    assert result.authority_reason == "INVALID_EXPIRY"


def test_issuer_deny_route_not_selected():
    result = collaborator().issue(
        req(routing_result=route("kilo-cli-agent", decision="REJECTED"))
    )
    assert result.authority_decision == "DENY"
    assert result.authority_reason == "ROUTE_NOT_SELECTED"


def test_issuer_exception():
    class Boom:
        def evaluate(self, request):
            raise RuntimeError("boom")

    result = ProductionAppAuthorityCollaborator(Boom()).issue(req())
    assert result.authority_reason.startswith("ISSUER_EXCEPTION:")


def test_kilo_fake_authority_issued():
    result = collaborator().issue(req(receiver_id="kilo-cli-agent", request_id="ea4e44-kilo"))
    assert result.authority_decision == "ISSUED"
    assert result.constructed_request_id == "ea4e44-kilo"
    assert result.constructed_receiver_id == "kilo-cli-agent"
    assert result.constructed_transport_id == QUALIFIED_RECEIVERS["kilo-cli-agent"][
        "transport_contract_id"
    ]
    assert result.constructed_model_binding_id == QUALIFIED_RECEIVERS["kilo-cli-agent"][
        "model_binding_id"
    ]
    assert result.issuance_result.authority_issued is True
    assert TRIPWIRE_HITS["executor"] == 0
    assert TRIPWIRE_HITS["binding"] == 0
    assert TRIPWIRE_HITS["invocation"] == 0


def test_opencode_fake_authority_issued():
    result = collaborator().issue(
        req(receiver_id="opencode-cli-agent", request_id="ea4e44-oc")
    )
    assert result.authority_decision == "ISSUED"
    assert result.constructed_receiver_id == "opencode-cli-agent"
    assert result.constructed_transport_id == QUALIFIED_RECEIVERS["opencode-cli-agent"][
        "transport_contract_id"
    ]
    assert result.constructed_model_binding_id == QUALIFIED_RECEIVERS["opencode-cli-agent"][
        "model_binding_id"
    ]


def test_kilo_with_opencode_transport():
    result = collaborator().issue(
        req(
            receiver_id="kilo-cli-agent",
            request_id="cross-t",
            transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"][
                "transport_contract_id"
            ],
        )
    )
    assert result.authority_decision == "DENY"
    assert result.authority_reason == "TRANSPORT_CONTRACT_MISMATCH"


def test_kilo_with_opencode_model():
    result = collaborator().issue(
        req(
            receiver_id="kilo-cli-agent",
            request_id="cross-m",
            model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
        )
    )
    assert result.authority_reason == "MODEL_BINDING_MISMATCH"


def test_opencode_with_kilo_transport():
    result = collaborator().issue(
        req(
            receiver_id="opencode-cli-agent",
            request_id="cross-ot",
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"][
                "transport_contract_id"
            ],
        )
    )
    assert result.authority_reason == "TRANSPORT_CONTRACT_MISMATCH"


def test_opencode_with_kilo_model():
    result = collaborator().issue(
        req(
            receiver_id="opencode-cli-agent",
            request_id="cross-om",
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        )
    )
    assert result.authority_reason == "MODEL_BINDING_MISMATCH"


def test_identical_inputs_same_decision():
    request = req(request_id="ea4e44-det")
    a = ProductionAppAuthorityCollaborator(
        ProductionIssuancePolicy(clock=ClockCollaborator(now=NOW))
    ).issue(request)
    b = ProductionAppAuthorityCollaborator(
        ProductionIssuancePolicy(clock=ClockCollaborator(now=NOW))
    ).issue(request)
    assert a.authority_decision == b.authority_decision == "ISSUED"
    assert a.authority_reason == b.authority_reason


def test_no_cache_across_requests():
    collab = collaborator()
    first = collab.issue(req(receiver_id="kilo-cli-agent", request_id="ea4e44-c1"))
    second = collab.issue(req(receiver_id="opencode-cli-agent", request_id="ea4e44-c2"))
    assert first.constructed_receiver_id == "kilo-cli-agent"
    assert second.constructed_receiver_id == "opencode-cli-agent"
    assert first.authority_decision == "ISSUED"
    assert second.authority_decision == "ISSUED"
