"""Non-live identity check before a delegated invocation issue request.

This preflight cannot issue or consume authorization. A later owner must
revalidate authority at claim time; this check is not a process-start gate.
"""

from tools.hermes_core.agent_invocation_bridge import AgentInvocationBridge
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.governed_bound_executor import GovernedExecutorResolution
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_invocation_authorization import (
    MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)


def build_agent_issue_request(
    bridge: AgentInvocationBridge,
    *,
    requested_ttl_seconds: int,
) -> ProductionInvocationAuthorizationIssueRequest:
    """Derive one stable issuer identity for an accepted attempt."""
    if (type(bridge) is not AgentInvocationBridge or not bridge.verify_hash()
            or type(requested_ttl_seconds) is not int
            or not 1 <= requested_ttl_seconds <= MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS):
        raise DelegationIntegrityError("agent issue request inputs denied")
    digest = sha256_payload({
        "schema_version": "ea4e92hh-agent-issue-identity-v1",
        "bridge_hash": bridge.artifact_hash,
    })
    return ProductionInvocationAuthorizationIssueRequest(
        issue_request_id="agent-issue-" + digest,
        execution_request_id=bridge.execution_request_id,
        receiver_id=bridge.receiver_agent_id,
        binding_id=bridge.executor_binding_id,
        enablement_id=bridge.executor_enablement_id,
        nonce="agent-nonce-" + digest,
        requested_ttl_seconds=requested_ttl_seconds,
    )


def preflight_agent_issue_request(
    store: SQLiteAgentInvocationBridgeStore,
    attempt_id: str,
    resolution: GovernedExecutorResolution,
    request: ProductionInvocationAuthorizationIssueRequest,
) -> AgentInvocationBridge:
    """Match an explicit issue request to an existing, active reservation."""
    if (type(store) is not SQLiteAgentInvocationBridgeStore
            or type(attempt_id) is not str or not attempt_id
            or type(resolution) is not GovernedExecutorResolution
            or type(request) is not ProductionInvocationAuthorizationIssueRequest):
        raise DelegationIntegrityError("agent issue preflight inputs denied")
    existing = store.get(attempt_id)
    if existing is None:
        raise DelegationIntegrityError("agent invocation reservation absent")
    current = store.reserve(attempt_id, resolution)
    if current != existing:
        raise DelegationIntegrityError("agent invocation reservation changed")
    if (request.execution_request_id != current.execution_request_id
            or request.receiver_id != current.receiver_agent_id
            or request.binding_id != current.executor_binding_id
            or request.enablement_id != current.executor_enablement_id):
        raise DelegationIntegrityError("agent issue request identity mismatch")
    expected = build_agent_issue_request(
        current, requested_ttl_seconds=request.requested_ttl_seconds,
    )
    if request != expected:
        raise DelegationIntegrityError("agent issue request replay identity mismatch")
    return current
