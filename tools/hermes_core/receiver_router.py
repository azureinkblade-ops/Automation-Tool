"""EA-4E.6 receiver router — fake/non-live qualification only.

This module implements a bounded receiver router that deterministically
selects a qualified receiver WITHOUT:

- executing any receiver process;
- invoking any model;
- creating execution authority;
- mutating receiver security policy;
- authorizing fallback/failover.

The router's sole responsibility is to map a canonical routing request to a
receiver selection decision. Execution remains gated by the separate
execution-authority boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.kilo_adapter import KILO_TRANSPORT_CONTRACT_ID
from tools.hermes_core.kilo_successor_binding import KILO_MODEL_BINDING_ID


# --------------------------------------------------------------------------- #
# Frozen qualified-receiver contract IDs (read-only; set by qualification)
# --------------------------------------------------------------------------- #

QUALIFIED_RECEIVERS: dict[str, dict[str, str]] = {
    "opencode-cli-agent": {
        "transport_contract_id": "192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f",
        "model_binding_id": "cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371",
        "receiver_class": "OPENCODE",
    },
    "kilo-cli-agent": {
        "transport_contract_id": KILO_TRANSPORT_CONTRACT_ID,
        "model_binding_id": KILO_MODEL_BINDING_ID,
        "receiver_class": "KILO",
    },
}


# --------------------------------------------------------------------------- #
# Routing request / result contracts
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RoutingRequest:
    """Canonical routing input.

    Only the ``receiver_id`` field controls router configuration.
    ``task_text`` is explicitly excluded from routing decisions.
    """
    receiver_id: str
    delegation_class: str = "governed"
    capability_requirements: Sequence[str] = ()
    execution_authority_present: bool = False


@dataclass(frozen=True)
class RoutingResult:
    """Bounded router result.

    ``execution_started`` is ALWAYS False for fake qualification.
    Routing success does NOT imply execution authorization.
    """
    receiver_id: Optional[str]
    qualification_state: str
    route_decision: str
    route_reason: str
    execution_authority_present: bool
    execution_started: bool = False


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #

class ReceiverRouter:
    """Deterministic receiver router — fake/non-live qualification only.

    The router selects a receiver based solely on the requested receiver ID
    and the frozen qualified-receiver set. It does NOT:

    - start any process;
    - invoke any model;
    - create execution authority;
    - mutate receiver policy;
    - authorize fallback.
    """

    ROUTER_SCHEMA_VERSION = "ea4e.6"
    ROUTER_SCHEMA_ID = "hermes.receiver-router/v1"

    def __init__(
        self,
        *,
        qualified_receivers: Optional[dict[str, dict[str, str]]] = None,
    ) -> None:
        self._qualified = qualified_receivers or QUALIFIED_RECEIVERS

    def route(self, request: RoutingRequest) -> RoutingResult:
        """Deterministically select a receiver.

        Returns a ``RoutingResult`` with ``execution_started=False``.
        """
        # Fail closed: empty receiver ID
        if not request.receiver_id:
            return RoutingResult(
                receiver_id=None,
                qualification_state="UNQUALIFIED",
                route_decision="REJECT",
                route_reason="EMPTY_RECEIVER_ID",
                execution_authority_present=request.execution_authority_present,
            )

        # Fail closed: unsupported receiver
        if request.receiver_id not in self._qualified:
            return RoutingResult(
                receiver_id=None,
                qualification_state="UNQUALIFIED",
                route_decision="REJECT",
                route_reason="UNSUPPORTED_RECEIVER",
                execution_authority_present=request.execution_authority_present,
            )

        # Receiver is qualified
        return RoutingResult(
            receiver_id=request.receiver_id,
            qualification_state="QUALIFIED",
            route_decision="SELECTED",
            route_reason="RECEIVER_QUALIFIED",
            execution_authority_present=request.execution_authority_present,
        )

    def verify_contract(
        self,
        *,
        receiver_id: str,
        expected_transport_contract_id: str,
    ) -> bool:
        """Verify a receiver's frozen contract matches the expected value.

        Returns True only if the receiver is qualified AND the contract
        identifier matches exactly. Any mismatch fails closed (False).
        """
        if receiver_id not in self._qualified:
            return False
        actual = self._qualified[receiver_id].get("transport_contract_id", "")
        return actual == expected_transport_contract_id

    def get_qualified_receivers(self) -> frozenset[str]:
        """Return the set of currently qualified receiver IDs."""
        return frozenset(self._qualified.keys())

    def get_canonical_material(self) -> dict[str, Any]:
        """Return deterministic canonical router material for hashing."""
        return {
            "schema_id": self.ROUTER_SCHEMA_ID,
            "schema_version": self.ROUTER_SCHEMA_VERSION,
            "qualified_receivers": {
                k: self._qualified[k] for k in sorted(self._qualified)
            },
            "fallback_policy": "NONE",
            "execution_authority_required": True,
            "routing_precedence": "EXPLICIT_RECEIVER_ID",
            "fail_closed_behaviors": [
                "EMPTY_RECEIVER_ID",
                "UNSUPPORTED_RECEIVER",
                "CONTRACT_MISMATCH",
            ],
        }

    def get_canonical_json(self) -> str:
        return canonical_json(self.get_canonical_material())

    def get_contract_id(self) -> str:
        """Compute the EA-4E.6 router contract ID."""
        return sha256_payload(self.get_canonical_material())


# --------------------------------------------------------------------------- #
# Module-level singleton for deterministic routing
# --------------------------------------------------------------------------- #

_default_router = ReceiverRouter()


def get_default_router() -> ReceiverRouter:
    """Return the default bounded receiver router."""
    return _default_router


def route_receiver(
    receiver_id: str,
    *,
    execution_authority_present: bool = False,
) -> RoutingResult:
    """Convenience wrapper around the default router."""
    request = RoutingRequest(
        receiver_id=receiver_id,
        execution_authority_present=execution_authority_present,
    )
    return _default_router.route(request)


def compute_ea4e6_router_contract_id() -> str:
    """Compute the canonical EA-4E.6 router contract ID."""
    return _default_router.get_contract_id()
