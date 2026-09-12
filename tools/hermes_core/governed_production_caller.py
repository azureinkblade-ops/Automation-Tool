"""EA-4E.29 explicit caller composition for governed production runtime.

The caller carries an explicit authorization-issuance request through an
already-resolved binding, the external EA-4E.28 issuer, and the consume-only
EA-4E.26 runtime. It does not select receivers or create bindings.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from tools.hermes_core.governed_bound_executor import (
    GovernedBoundExecutorResolver,
    compute_ea4e22_integration_contract_id,
)
from tools.hermes_core.governed_production_runtime import (
    GovernedProductionRuntime,
    GovernedProductionRuntimeRequest,
    GovernedProductionRuntimeResult,
    compute_ea4e26_integration_contract_id,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
    ProductionInvocationAuthorizationIssuer,
    compute_ea4e28_issuer_contract_id,
)


CALLER_SCHEMA_ID = "hermes.governed-production-caller/v2"
CALLER_SCHEMA_VERSION = "ea4e.29r1"
CALLER_ARTIFACT_VERSION = "2"

LEGACY_EA4E29_CALLER_CONTRACT_ID = (
    "aa9b2e1a6bb2307e814bb66913f7fdb8134a3fbb0273bfb8be000da6e480ee9a"
)


@dataclass(frozen=True)
class GovernedProductionCallerRequest:
    runtime_request: GovernedProductionRuntimeRequest
    authorization_issue_request: ProductionInvocationAuthorizationIssueRequest | None


@dataclass(frozen=True)
class GovernedProductionCallerResult:
    caller_decision: str
    caller_reason: str
    resolution_decision: str = "NOT_EVALUATED"
    issuance_decision: str = "NOT_EVALUATED"
    runtime_result: GovernedProductionRuntimeResult | None = None


class GovernedProductionCaller:
    """Compose explicit issuance and runtime consumption without fabrication."""

    def __init__(
        self,
        *,
        resolver: GovernedBoundExecutorResolver,
        issuer: ProductionInvocationAuthorizationIssuer,
        runtime: GovernedProductionRuntime,
    ) -> None:
        self._resolver = resolver
        self._issuer = issuer
        self._runtime = runtime

    def invoke(
        self, request: GovernedProductionCallerRequest
    ) -> GovernedProductionCallerResult:
        runtime_request = request.runtime_request
        issue_request = request.authorization_issue_request
        if issue_request is None:
            return self._deny("AUTHORIZATION_ISSUE_REQUEST_REQUIRED")
        if runtime_request.invocation_authorization is not None:
            return self._deny("AMBIGUOUS_AUTHORIZATION_SOURCE")
        if issue_request.execution_request_id != runtime_request.request_id:
            return self._deny("EXECUTION_REQUEST_ID_MISMATCH")
        if issue_request.receiver_id != runtime_request.receiver_id:
            return self._deny("RECEIVER_ID_MISMATCH")

        resolution = self._resolver.resolve_governed_executor(runtime_request.receiver_id)
        if resolution.resolution_decision != "RESOLVED":
            return GovernedProductionCallerResult(
                caller_decision="DENY",
                caller_reason=f"RESOLUTION_REJECTED:{resolution.resolution_reason}",
                resolution_decision=resolution.resolution_decision,
            )

        issue_result = self._issuer.issue(issue_request, resolution)
        if issue_result.policy_decision != "ALLOW" or issue_result.authorization is None:
            return GovernedProductionCallerResult(
                caller_decision="DENY",
                caller_reason=f"ISSUANCE_REJECTED:{issue_result.policy_reason}",
                resolution_decision="RESOLVED",
                issuance_decision=issue_result.policy_decision,
            )

        runtime_result = self._runtime.execute(
            replace(
                runtime_request,
                invocation_authorization=issue_result.authorization,
            )
        )
        return GovernedProductionCallerResult(
            caller_decision=(
                "EXECUTED" if runtime_result.ea4e26_disposition == "PASS" else "DENY"
            ),
            caller_reason=runtime_result.reason,
            resolution_decision="RESOLVED",
            issuance_decision="ALLOW",
            runtime_result=runtime_result,
        )

    @staticmethod
    def _deny(reason: str) -> GovernedProductionCallerResult:
        return GovernedProductionCallerResult(
            caller_decision="DENY", caller_reason=reason
        )


def ea4e29_caller_contract_payload() -> dict[str, object]:
    """Return the canonical restart-durable caller contract payload."""
    return {
        "schema_id": CALLER_SCHEMA_ID,
        "schema_version": CALLER_SCHEMA_VERSION,
        "artifact_version": CALLER_ARTIFACT_VERSION,
        "ea4e22_integration_contract_id": compute_ea4e22_integration_contract_id(),
        "ea4e26_integration_contract_id": compute_ea4e26_integration_contract_id(),
        "ea4e28_issuer_contract_id": compute_ea4e28_issuer_contract_id(),
        "explicit_receiver_required": True,
        "explicit_issue_request_required": True,
        "prepopulated_authorization": "DENY",
        "request_identity_match_required": True,
        "receiver_identity_match_required": True,
        "preexisting_resolution_required": True,
        "runtime_is_not_issuer": True,
        "receives_only_durably_committed_authorization": True,
        "passes_authorization_explicitly_to_runtime": True,
        "authorization_synthesis": False,
        "issuer_bypass": False,
        "durable_store_bypass": False,
        "auto_reissue_after_deny": False,
        "auto_refresh_expired_authorization": False,
        "direct_receiver_execution": False,
        "receiver_selection": False,
        "binding_creation": False,
        "retry": False,
        "fallback": False,
        "failover": False,
    }


def compute_ea4e29_caller_contract_id() -> str:
    return sha256_payload(ea4e29_caller_contract_payload())
