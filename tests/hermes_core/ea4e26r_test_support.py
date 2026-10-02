from tools.hermes_core.production_app_authority import (
    ProductionAppAuthorityCollaborator,
    ProductionAppAuthorityRequest,
)
from tools.hermes_core.production_issuance import (
    ClockCollaborator,
    ProductionIssuancePolicy,
    QUALIFIED_RECEIVERS,
)
from tools.hermes_core.receiver_router import (
    RoutingRequest,
    compute_ea4e6_router_contract_id,
    get_default_router,
)


QUALIFICATION_CLOCK = "2026-01-01T00:00:00Z"


def external_authority_and_activation(
    receiver_id: str,
    request_id: str,
    *,
    clock: ClockCollaborator | None = None,
):
    clock = clock or ClockCollaborator(now=QUALIFICATION_CLOCK)
    receiver = QUALIFIED_RECEIVERS[receiver_id]
    route = get_default_router().route(RoutingRequest(receiver_id=receiver_id))
    result = ProductionAppAuthorityCollaborator(
        ProductionIssuancePolicy(clock=clock)
    ).issue(
        ProductionAppAuthorityRequest(
            execution_request_id=request_id,
            receiver_id=receiver_id,
            transport_contract_id=receiver["transport_contract_id"],
            model_binding_id=receiver["model_binding_id"],
            router_contract_id=compute_ea4e6_router_contract_id(),
            delegation_class="governed",
            requested_operation="receiver-dispatch",
            requested_execution_scope="production",
            requested_attempt_limit=1,
            requested_authority_ttl_seconds=3600,
            request_nonce=f"external-{request_id}",
            routing_result=route,
        )
    )
    assert result.authority_decision == "ISSUED"
    assert result.issuance_result is not None
    assert result.issuance_result.authority is not None
    assert result.issuance_result.activation is not None
    return result.issuance_result.authority, result.issuance_result.activation
