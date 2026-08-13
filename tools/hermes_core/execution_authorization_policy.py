"""Execution-authorization policy contracts (EA-3I.1, pure/read-only).

This module defines the *policy* half of the EA-3I.1 evaluation slice. It is
deliberately PRE-CAPABILITY: it defines deterministic, versioned policy
contracts and resolution, but it never builds or persists an
``ExecutionAuthorization`` and never calls the EA-3B atomic-grant store.

Policies are authoritative, versioned, and loaded from repository data
(``tools/hermes_core/policies/*.yaml``). Resolution is deterministic: the
caller cannot select an arbitrary policy unchecked; the resolved policy must
bind ``policy_id`` + ``policy_version`` exactly.

ACCEPTED != EXECUTION AUTHORIZATION is preserved: a policy evaluation is only
an eligibility opinion, never an authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

from .execution_authorization import ExecutionAuthorizationActorType

# --------------------------------------------------------------------------- #
# Policy decision vocabulary
# --------------------------------------------------------------------------- #


class ExecutionAuthorizationPolicyDecision(str, Enum):
    """Outcome of a pure policy evaluation.

    None of these results creates authority. They are eligibility opinions
    only; the capability-bearing issuance operation (EA-3I.2+) remains
    separately authorized and is never invoked from this module.
    """

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"


# --------------------------------------------------------------------------- #
# Policy errors
# --------------------------------------------------------------------------- #


class ExecutionAuthorizationPolicyError(ValueError):
    """Base class for policy-layer errors."""


class ExecutionAuthorizationPolicyNotFoundError(ExecutionAuthorizationPolicyError):
    """The requested policy id (or id+version) is not registered."""


class ExecutionAuthorizationPolicyVersionError(ExecutionAuthorizationPolicyError):
    """The policy id is known but the requested version is unsupported."""


class ExecutionAuthorizationPolicyMalformedError(ExecutionAuthorizationPolicyError):
    """A policy document fails structural validation."""


# --------------------------------------------------------------------------- #
# Policy model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _AutoScope:
    """An explicitly enumerated (operation, worker_class) pair that a
    POLICY_SERVICE actor may auto-authorize without human sign-off."""

    operation: str
    # worker_class may be None meaning "deferred/unresolved" is acceptable for
    # this auto-scope (still not unrestricted: it must be enumerated).
    worker_class: Optional[str]


@dataclass(frozen=True)
class ExecutionAuthorizationPolicy:
    """A deterministic, versioned execution-authorization policy contract.

    Conservative default posture:
    - POLICY_SERVICE auto-authorizable scopes = NONE unless explicitly
      enumerated in ``auto_scopes``;
    - SYSTEM cannot grant by default;
    - unknown operations / worker classes fail closed (DENY / REQUIRES_HUMAN);
    - requested authority is never widened (see constrain below).
    """

    policy_id: str
    policy_version: str
    description: str
    # Actor types this policy may ever consider eligible.
    allowed_actor_types: frozenset[ExecutionAuthorizationActorType]
    # authority_role values (per actor type) that may be eligible for ALLOW.
    allowed_roles: frozenset[str]
    # Explicitly enumerated POLICY_SERVICE auto-scopes (otherwise REQUIRES_HUMAN).
    auto_scopes: frozenset[_AutoScope] = field(default_factory=frozenset)
    # Operations this policy recognizes. Unknown operations fail closed.
    known_operations: frozenset[str] = field(default_factory=frozenset)
    # Worker classes this policy recognizes. None may be present to mean
    # "deferred/unresolved is permitted (subject to REQUIRES_HUMAN)".
    known_worker_classes: frozenset[Optional[str]] = field(default_factory=frozenset)
    # Attempt/runtime ceilings (never widened; constrained or DENY).
    max_attempt_limit: int = 1
    max_runtime_seconds: Optional[int] = 600
    # Expiry policy metadata (pure bounds; no real issued_at/expires_at here).
    null_expiry_allowed: bool = False
    max_authorization_lifetime_seconds: Optional[int] = None

    def allows_role(self, actor_type: ExecutionAuthorizationActorType, role: str) -> bool:
        return actor_type in self.allowed_actor_types and role in self.allowed_roles

    def auto_scope_for(
        self, operation: str, worker_class: Optional[str]
    ) -> bool:
        return _AutoScope(operation, worker_class) in self.auto_scopes


# --------------------------------------------------------------------------- #
# Registry loading (deterministic, versioned)
# --------------------------------------------------------------------------- #


_POLICIES_DIR = Path(__file__).resolve().parent / "policies"
_REGISTRY: dict[tuple[str, str], ExecutionAuthorizationPolicy] = {}


def _coerce_worker_class(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ExecutionAuthorizationPolicyMalformedError(
        f"worker_class must be a string or null, got {type(value).__name__}"
    )


def _load_policy_document(doc: dict[str, Any]) -> ExecutionAuthorizationPolicy:
    pid = doc.get("policy_id")
    pver = doc.get("policy_version")
    if not isinstance(pid, str) or not pid:
        raise ExecutionAuthorizationPolicyMalformedError("policy_id must be a non-empty string")
    if not isinstance(pver, str) or not pver:
        raise ExecutionAuthorizationPolicyMalformedError("policy_version must be a non-empty string")
    try:
        allowed_types = frozenset(
            ExecutionAuthorizationActorType(t) for t in doc.get("allowed_actor_types", [])
        )
    except ValueError as exc:
        raise ExecutionAuthorizationPolicyMalformedError(f"invalid actor type: {exc}") from exc
    auto_scopes = frozenset(
        _AutoScope(s["operation"], _coerce_worker_class(s.get("worker_class")))
        for s in doc.get("auto_scopes", [])
    )
    known_wc = frozenset(_coerce_worker_class(w) for w in doc.get("known_worker_classes", []))
    return ExecutionAuthorizationPolicy(
        policy_id=pid,
        policy_version=pver,
        description=doc.get("description", ""),
        allowed_actor_types=allowed_types,
        allowed_roles=frozenset(doc.get("allowed_roles", [])),
        auto_scopes=auto_scopes,
        known_operations=frozenset(doc.get("known_operations", [])),
        known_worker_classes=known_wc,
        max_attempt_limit=int(doc.get("max_attempt_limit", 1)),
        max_runtime_seconds=doc.get("max_runtime_seconds", 600),
        null_expiry_allowed=bool(doc.get("null_expiry_allowed", False)),
        max_authorization_lifetime_seconds=doc.get("max_authorization_lifetime_seconds"),
    )


def load_policy_registry() -> dict[tuple[str, str], ExecutionAuthorizationPolicy]:
    """Load all versioned policies from the repository policies directory.

    Deterministic: each (policy_id, policy_version) becomes one registry entry.
    A duplicate (id, version) raises Malformed (fail closed), never silently
    overwrites.
    """
    registry: dict[tuple[str, str], ExecutionAuthorizationPolicy] = {}
    if _POLICIES_DIR.is_dir():
        for path in sorted(_POLICIES_DIR.glob("*.yaml")):
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            docs = data if isinstance(data, list) else [data]
            for doc in docs:
                policy = _load_policy_document(doc)
                key = (policy.policy_id, policy.policy_version)
                if key in registry:
                    raise ExecutionAuthorizationPolicyMalformedError(
                        f"duplicate policy {policy.policy_id} v{policy.policy_version}"
                    )
                registry[key] = policy
    return registry


def get_policy_registry() -> dict[tuple[str, str], ExecutionAuthorizationPolicy]:
    """Return the process-wide cached registry (loaded once, immutable view)."""
    if not _REGISTRY:
        _REGISTRY.update(load_policy_registry())
    return dict(_REGISTRY)


def resolve_policy(
    policy_id: str, policy_version: str
) -> ExecutionAuthorizationPolicy:
    """Deterministically resolve a policy by (id, version).

    Missing id -> ExecutionAuthorizationPolicyNotFoundError (NOT a DENY).
    Known id, unsupported version -> ExecutionAuthorizationPolicyVersionError
    (NOT a DENY). Neither error is a policy refusal; they are evaluation
    preconditions that must surface as errors.
    """
    registry = get_policy_registry()
    if (policy_id, policy_version) in registry:
        return registry[(policy_id, policy_version)]
    if any(pid == policy_id for (pid, _v) in registry):
        raise ExecutionAuthorizationPolicyVersionError(
            f"policy {policy_id} known but version {policy_version} unsupported"
        )
    raise ExecutionAuthorizationPolicyNotFoundError(
        f"policy {policy_id} v{policy_version} not found"
    )
