"""Durable delegated authorization claim and start fence, without execution.

FENCED means a receiver start is irrevocably reserved, not that a process ran.
Any ambiguity after authorization consumption remains UNKNOWN on replay.
"""

from dataclasses import dataclass
import sqlite3
from contextlib import closing

from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_invocation_issue_preflight import (
    build_agent_issue_request, preflight_agent_issue_request,
)
from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError, _parse_timestamp
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableAuthorizationStoreError, DurableInvocationAuthorizationStore,
)
from tools.hermes_core.governed_bound_executor import GovernedExecutorResolution
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_invocation_authorization import (
    ProductionInvocationAuthorization, ProductionInvocationAuthorizationPolicy,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_executor_binding import parse_iso_timestamp


@dataclass(frozen=True)
class DelegatedClaimState:
    status: str
    reason: str
    authorization_id: str | None = None
    fence_hash: str | None = None


class AgentDelegatedClaimOwner:
    """Own two durable claims; never starts a receiver or creates a result."""

    def __init__(self, bridge_store: SQLiteAgentInvocationBridgeStore,
                 fence_store: SQLiteAgentReceiverStartFenceStore,
                 authorization_store: DurableInvocationAuthorizationStore,
                 *, clock, ttl_seconds: int = 60):
        if (type(bridge_store) is not SQLiteAgentInvocationBridgeStore
                or type(fence_store) is not SQLiteAgentReceiverStartFenceStore
                or type(authorization_store) is not DurableInvocationAuthorizationStore
                or bridge_store.authority is not fence_store.authority
                or bridge_store.start is not fence_store.start
                or not callable(getattr(clock, "now_iso", None))):
            raise DelegationIntegrityError("delegated claim owner stores denied")
        self.bridge_store = bridge_store
        self.fence_store = fence_store
        self.authorization_store = authorization_store
        self.clock = clock
        self.ttl_seconds = ttl_seconds
        self.issuer = ProductionInvocationAuthorizationIssuer(
            clock=clock, store=authorization_store,
        )
        self.policy = ProductionInvocationAuthorizationPolicy(
            clock=clock, store=authorization_store,
        )
        with closing(self._connect_authority()) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS agent_invocation_auth_store_bindings ("
                "attempt_id TEXT PRIMARY KEY, store_instance_id TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS agent_invocation_claim_intents ("
                "attempt_id TEXT PRIMARY KEY, authorization_id TEXT NOT NULL, "
                "execution_request_id TEXT NOT NULL, store_instance_id TEXT NOT NULL)"
            )
            conn.commit()

    def _connect_authority(self):
        conn = sqlite3.connect(self.bridge_store.authority.path, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _check_store_binding(self, attempt_id: str, *, insert: bool) -> None:
        store_id = self.authorization_store.store_instance_id
        with closing(self._connect_authority()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT store_instance_id FROM agent_invocation_auth_store_bindings "
                    "WHERE attempt_id=?", (attempt_id,),
                ).fetchone()
                if row is None and insert:
                    conn.execute(
                        "INSERT INTO agent_invocation_auth_store_bindings VALUES(?,?)",
                        (attempt_id, store_id),
                    )
                elif row != (store_id,):
                    raise DelegationIntegrityError("delegated authorization store identity mismatch")
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _request(self, attempt_id: str, resolution: GovernedExecutorResolution):
        self._check_lease_window(attempt_id)
        bridge = self.bridge_store.get(attempt_id)
        if bridge is None:
            raise DelegationIntegrityError("delegated invocation bridge absent")
        request = build_agent_issue_request(
            bridge, requested_ttl_seconds=self.ttl_seconds,
        )
        preflight_agent_issue_request(
            self.bridge_store, attempt_id, resolution, request,
        )
        return bridge, request

    def _claim_intent_exists(self, attempt_id: str) -> bool:
        with closing(self._connect_authority()) as conn:
            return conn.execute(
                "SELECT 1 FROM agent_invocation_claim_intents WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone() is not None

    def _record_claim_intent(self, attempt_id: str,
                             authorization: ProductionInvocationAuthorization) -> bool:
        store_id = self.authorization_store.store_instance_id
        with closing(self._connect_authority()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT 1 FROM agent_invocation_claim_intents WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone()
                if existing is not None:
                    conn.rollback()
                    return False
                conn.execute(
                    "INSERT INTO agent_invocation_claim_intents VALUES(?,?,?,?)",
                    (attempt_id, authorization.invocation_authorization_id,
                     authorization.execution_request_id, store_id),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def _check_lease_window(self, attempt_id: str) -> None:
        witness = load_bound_agent_start(
            self.bridge_store.authority, self.bridge_store.start, attempt_id,
        )
        try:
            now = parse_iso_timestamp(self.clock.now_iso())
            start_at = _parse_timestamp(witness.start_result.recorded_at)
            expires_at = _parse_timestamp(witness.lease.expires_at)
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("delegated claim clock invalid") from exc
        if not start_at <= now < expires_at:
            raise DelegationIntegrityError("delegated claim outside lease window")

    def issue(self, attempt_id: str, resolution: GovernedExecutorResolution):
        """Issue only the exact reserved request; this grants no process start."""
        if self._claim_intent_exists(attempt_id):
            raise DelegationIntegrityError("delegated claim intent already recorded")
        bridge, request = self._request(attempt_id, resolution)
        self._check_store_binding(attempt_id, insert=True)
        result = self.issuer.issue(request, resolution)
        if result.policy_decision == "ALLOW" and (
            result.authorization is None
            or result.authorization.execution_request_id != bridge.execution_request_id
            or result.authorization.receiver_id != bridge.receiver_agent_id
            or result.authorization.binding_id != bridge.executor_binding_id
            or result.authorization.enablement_id != bridge.executor_enablement_id
            or result.authorization.nonce != request.nonce
        ):
            raise DelegationIntegrityError("delegated issuer returned divergent identity")
        return result

    def claim_and_fence(
        self, attempt_id: str, resolution: GovernedExecutorResolution,
        authorization: ProductionInvocationAuthorization,
    ) -> DelegatedClaimState:
        """Consume once, then fence once; never return an execution permit."""
        if type(authorization) is not ProductionInvocationAuthorization:
            return DelegatedClaimState("DENIED", "INVALID_AUTHORIZATION")
        intent_recorded = False
        try:
            self._check_store_binding(attempt_id, insert=False)
            if self._claim_intent_exists(attempt_id):
                return DelegatedClaimState("UNKNOWN", "CLAIM_INTENT_ALREADY_RECORDED")
            if self.fence_store.get(attempt_id) is not None:
                return DelegatedClaimState("UNKNOWN", "RECEIVER_START_ALREADY_CLAIMED")
            state = self.authorization_store.inspect(authorization.to_canonical_dict())
            if state.consumed:
                return DelegatedClaimState("UNKNOWN", "AUTHORIZATION_ALREADY_CONSUMED")
            bridge, request = self._request(attempt_id, resolution)
            issued = self.authorization_store.get_issued(
                request.issue_request_id, sha256_payload(request.to_canonical_dict()),
            )
            if issued is None or issued.authorization_payload != authorization.to_canonical_dict():
                return DelegatedClaimState("DENIED", "ISSUED_IDENTITY_MISMATCH")
            intent_recorded = self._record_claim_intent(attempt_id, authorization)
            if not intent_recorded:
                return DelegatedClaimState("UNKNOWN", "CLAIM_INTENT_ALREADY_RECORDED")
            result = self.policy.claim_for_execution(
                authorization, resolution.binding_handle, {},
                expected_execution_request_id=bridge.execution_request_id,
            )
            if result.policy_decision != "ALLOW":
                return DelegatedClaimState("UNKNOWN", result.policy_reason)
        except (DurableAuthorizationStoreError, sqlite3.Error):
            return DelegatedClaimState("UNKNOWN", "AUTHORIZATION_STATE_UNCERTAIN")
        except DelegationIntegrityError as exc:
            return DelegatedClaimState(
                "UNKNOWN" if intent_recorded else "DENIED", str(exc),
            )
        except Exception:
            if intent_recorded:
                return DelegatedClaimState("UNKNOWN", "CLAIM_AFTER_INTENT_UNCERTAIN")
            raise
        try:
            self._check_lease_window(attempt_id)
            fence = self.fence_store.claim(attempt_id)
        except Exception:
            return DelegatedClaimState(
                "UNKNOWN", "FENCE_AFTER_AUTHORIZATION_CLAIM_UNCERTAIN",
                authorization.invocation_authorization_id,
            )
        return DelegatedClaimState(
            "FENCED", "NO_RECEIVER_STARTED",
            authorization.invocation_authorization_id, fence.claim_hash,
        )
