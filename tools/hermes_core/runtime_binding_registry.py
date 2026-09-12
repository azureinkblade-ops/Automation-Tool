"""EA-4D.3A: trusted runtime-binding registry + deterministic resolver.

This slice implements ONLY:

    WorkerRouteDecision
            |
            v
    trusted exact binding lookup
            |
            v
    VALIDATED WorkerRuntimeBinding
            |
            X STOP

It ends at a validated ``WorkerRuntimeBinding``. It does NOT:

    * construct or persist an ``ExecutionLaunchAttempt``,
    * append ``LAUNCH_ATTEMPT_RECORDED``,
    * invoke any adapter or worker,
    * create a process / perform HTTP / network / filesystem discovery,
    * transition to ``EXECUTING``.

Architecture (EA-4D.3 design, Option D - hybrid)
-------------------------------------------------
The authoritative runtime-binding source of truth is a trusted, static,
versioned, in-process registry. The registry is immutable, deterministic,
hash-bound, order-canonicalized, and duplicate-safe. EA-4D.3B/3E later copy the
resolved binding's ``id/version/hash`` into the durable ``ExecutionLaunchAttempt``
as provenance -- but no such durable artifact is created in this slice.

Security boundary
-----------------
* ``configuration_reference`` is symbolic trusted metadata only (e.g.
  ``"hermes-worker-local-v1"``). Raw executable text, shell prefixes, arbitrary
  URLs, and absolute executable paths are structurally rejected.
* ``adapter_kind`` is validated against the frozen ``WorkerRuntimeAdapterKind``
  enum. Unknown kinds fail closed.
* The resolver performs no fallback: no alternate worker, no version fallback,
  no class-only fallback, no re-routing through ``WorkerRouter``.

This module is pure with respect to external side effects: no sqlite3, no
subprocess/os.system/Popen, no network clients, no filesystem/environment
discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from tools.hermes_core.execution_start import (
    canonical_json,
    ExecutionRuntimeBindingError,
    ExecutionRuntimeBindingIntegrityError,
    ExecutionRuntimeBindingMismatchError,
    ExecutionRuntimeBindingNotFoundError,
    sha256_payload,
    WorkerRuntimeAdapterKind,
    WorkerRuntimeBinding,
)


# --------------------------------------------------------------------------- #
# Narrowly-scoped errors introduced by EA-4D.3A (packet section 21)
# --------------------------------------------------------------------------- #


class ExecutionRuntimeBindingDisabledError(ExecutionRuntimeBindingError):
    """Binding exists but ``enabled == False``."""


class ExecutionRuntimeBindingIdempotencyRequiredError(ExecutionRuntimeBindingError):
    """Binding does not support idempotency; cannot be admitted by EA-4D.3B/3E."""


class ExecutionRuntimeBindingRegistryError(ExecutionRuntimeBindingError):
    """Registry construction or structural violation."""


class ExecutionRuntimeBindingRegistryConflictError(
    ExecutionRuntimeBindingRegistryError
):
    """Duplicate exact identity (worker_id, worker_version, worker_class)."""


# --------------------------------------------------------------------------- #
# Registry artifact (immutable, hash-bound, order-canonicalized)
# --------------------------------------------------------------------------- #


def _binding_sort_key(b: WorkerRuntimeBinding) -> Tuple:
    return (
        b.worker_id or "",
        b.worker_version or "",
        b.worker_class or "",
        b.runtime_binding_id or "",
    )


@dataclass(frozen=True)
class WorkerRuntimeBindingRegistry:
    """Immutable, hash-bound collection of trusted runtime bindings.

    Construction is performed exclusively through
    :func:`build_worker_runtime_binding_registry`, which canonicalizes binding
    order, rejects duplicate exact identities, and computes a deterministic
    registry hash.
    """

    registry_version: str
    artifact_hash: str
    bindings: Tuple[WorkerRuntimeBinding, ...] = field(default_factory=tuple)
    registration_source: Optional[str] = None
    registration_version: Optional[str] = None

    def to_canonical_dict(self) -> dict:
        # Canonical ordering makes [A, B] and [B, A] hash-identical when they
        # contain the same logical bindings.
        ordered = sorted(self.bindings, key=_binding_sort_key)
        return {
            "registry_version": self.registry_version,
            "bindings": [b.to_canonical_dict() for b in ordered],
            "registration_source": self.registration_source,
            "registration_version": self.registration_version,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


# --------------------------------------------------------------------------- #
# Pure builder (no persistence, no clock, no network/process)
# --------------------------------------------------------------------------- #


def _is_shell_like_reference(value: str) -> bool:
    """Structural rejection of obviously executable/task-controlled references.

    This is intentionally NOT a shell parser. It rejects:
      * empty strings,
      * raw command prefixes (powershell, cmd.exe, bash -c, sh -c, ...),
      * arbitrary http(s):// URLs,
      * absolute executable paths (drive-rooted or leading '/') which are
        executable-location signals rather than symbolic references.

    Symbolic trusted references (e.g. "hermes-worker-local-v1") pass.
    """
    if not value:
        return True
    lowered = value.strip().lower()
    if not lowered:
        return True
    shell_prefixes = (
        "powershell",
        "cmd.exe",
        "bash",
        "sh -c",
        "sh ",
        "pwsh",
        "python -c",
        "python3 -c",
        "cmd /c",
    )
    for prefix in shell_prefixes:
        if lowered.startswith(prefix):
            return True
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return True
    # Absolute path heuristics (Windows drive-root or POSIX root) are rejected
    # because they are executable-location signals, not symbolic references.
    if len(value) >= 2 and value[1] == ":" and value[2:3] in ("\\", "/"):
        return True
    if value.startswith("/") or value.startswith("\\"):
        return True
    return False


def _validate_configuration_reference(value: str) -> None:
    if _is_shell_like_reference(value):
        raise ExecutionRuntimeBindingIntegrityError(
            f"configuration_reference is not a symbolic trusted reference: {value!r}"
        )


def _validate_binding_integrity(b: WorkerRuntimeBinding) -> None:
    """Reuse the binding's own hash integrity; structurally reject bad metadata."""
    if not isinstance(b, WorkerRuntimeBinding):
        raise ExecutionRuntimeBindingIntegrityError(
            "registry binding is not a WorkerRuntimeBinding"
        )
    # Validate adapter_kind TYPE first. verify_hash() below calls
    # to_canonical_dict() which dereferences adapter_kind.value -- a str
    # adapter_kind would raise AttributeError before this check is reached.
    if not isinstance(b.adapter_kind, WorkerRuntimeAdapterKind):
        raise ExecutionRuntimeBindingIntegrityError(
            f"adapter_kind {b.adapter_kind!r} is not a valid WorkerRuntimeAdapterKind"
        )
    if not b.verify_hash():
        raise ExecutionRuntimeBindingIntegrityError(
            f"runtime binding {b.runtime_binding_id} failed hash verification"
        )
    if not b.worker_id:
        raise ExecutionRuntimeBindingIntegrityError("worker_id is required")
    if not b.worker_version:
        raise ExecutionRuntimeBindingIntegrityError("worker_version is required")
    if (
        b.adapter_version is None
        or b.adapter_version.strip().lower()
        in ("", "*", "latest", "none", "wildcard")
    ):
        raise ExecutionRuntimeBindingIntegrityError(
            f"adapter_version must be explicit and immutable, got {b.adapter_version!r}"
        )
    if not _well_formed_canonical_hash(b.configuration_hash):
        raise ExecutionRuntimeBindingIntegrityError(
            "configuration_hash must be a present, well-formed canonical hash"
        )
    _validate_configuration_reference(b.configuration_reference)


def _well_formed_canonical_hash(value: str) -> bool:
    """A canonical hash is a 64-char lowercase hex SHA-256 digest."""
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def build_worker_runtime_binding_registry(
    *,
    registry_version: str,
    bindings: List[WorkerRuntimeBinding],
    registration_source: Optional[str] = None,
    registration_version: Optional[str] = None,
) -> WorkerRuntimeBindingRegistry:
    """Build an immutable, hash-bound, order-canonicalized registry.

    * Validates every binding (hash + metadata).
    * Canonicalizes binding order (sorted by identity).
    * Rejects duplicate exact identities (worker_id, worker_version,
      worker_class) -- FAIL CLOSED, no first/last/insertion-order selection.
    * Computes a deterministic registry hash.
    * Performs NO persistence, NO clock read, NO network/process operation.
    """
    if not registry_version:
        raise ExecutionRuntimeBindingRegistryError("registry_version is required")
    if bindings is None:
        raise ExecutionRuntimeBindingRegistryError("bindings is required")

    seen_identities = set()
    canonical_bindings: List[WorkerRuntimeBinding] = []
    for b in bindings:
        _validate_below(b)
        identity = (b.worker_id, b.worker_version, b.worker_class)
        if identity in seen_identities:
            raise ExecutionRuntimeBindingRegistryConflictError(
                "duplicate exact runtime-binding identity "
                f"(worker_id={b.worker_id}, worker_version={b.worker_version}, "
                f"worker_class={b.worker_class}); registry rejects duplicate "
                "exact identities (fail-closed)"
            )
        seen_identities.add(identity)
        canonical_bindings.append(b)

    partial = WorkerRuntimeBindingRegistry(
        registry_version=registry_version,
        artifact_hash="",
        bindings=tuple(canonical_bindings),
        registration_source=registration_source,
        registration_version=registration_version,
    )
    artifact_hash = sha256_payload(partial.to_canonical_dict())
    return WorkerRuntimeBindingRegistry(
        registry_version=registry_version,
        artifact_hash=artifact_hash,
        bindings=tuple(canonical_bindings),
        registration_source=registration_source,
        registration_version=registration_version,
    )


def _validate_below(b: WorkerRuntimeBinding) -> None:
    """Validate a single binding intended for the registry (hash + metadata)."""
    _validate_binding_integrity(b)


# --------------------------------------------------------------------------- #
# Resolver (pure, deterministic; no routing/fallback/invocation)
# --------------------------------------------------------------------------- #


def resolve_worker_runtime_binding(
    *,
    registry: WorkerRuntimeBindingRegistry,
    worker_id: str,
    worker_version: str,
    worker_class: Optional[str],
    operation: str,
) -> WorkerRuntimeBinding:
    """Resolve the exact trusted runtime binding for a selected worker identity.

    Required exact identity match (no partial / version / class fallback):
        binding.worker_id      == worker_id
        binding.worker_version == worker_version
        binding.worker_class   == worker_class

    Then:
        * operation must be in binding.allowed_operations,
        * binding.enabled must be True,
        * binding.supports_idempotency must be True,
        * binding.adapter_kind must be a valid WorkerRuntimeAdapterKind,
        * binding.adapter_version must be explicit,
        * binding.configuration_reference must be symbolic (not executable),
        * binding.configuration_hash must be well-formed.

    On any failure the resolver FAILS CLOSED with a typed error. It never
    selects another worker, another version, another class, or re-invokes
    WorkerRouter.
    """
    if not isinstance(registry, WorkerRuntimeBindingRegistry):
        raise ExecutionRuntimeBindingRegistryError(
            "registry must be a WorkerRuntimeBindingRegistry"
        )
    if not registry.verify_hash():
        raise ExecutionRuntimeBindingRegistryError(
            "registry failed hash verification"
        )
    if not worker_id:
        raise ExecutionRuntimeBindingNotFoundError("worker_id is required")
    if not worker_version:
        raise ExecutionRuntimeBindingNotFoundError("worker_version is required")

    candidate: Optional[WorkerRuntimeBinding] = None
    for b in registry.bindings:
        if (
            b.worker_id == worker_id
            and b.worker_version == worker_version
            and b.worker_class == worker_class
        ):
            candidate = b
            break

    if candidate is None:
        raise ExecutionRuntimeBindingNotFoundError(
            f"no exact runtime binding for worker_id={worker_id}, "
            f"worker_version={worker_version}, worker_class={worker_class} "
            "(fail-closed; no fallback worker selected)"
        )

    # Re-validate integrity of the resolved binding defensively (registry was
    # already validated at build time; this guards against hand-built
    # registries passed without construction).
    _validate_binding_integrity(candidate)

    if candidate.enabled is not True:
        raise ExecutionRuntimeBindingDisabledError(
            f"runtime binding {candidate.runtime_binding_id} is disabled"
        )

    if candidate.supports_idempotency is not True:
        raise ExecutionRuntimeBindingIdempotencyRequiredError(
            f"runtime binding {candidate.runtime_binding_id} does not support "
            "idempotency; EA-4D.3B/3E cannot admit it (fail-closed)"
        )

    ops = sorted(set(candidate.allowed_operations or []))
    if operation not in ops:
        raise ExecutionRuntimeBindingMismatchError(
            f"operation {operation!r} not allowed by binding "
            f"{candidate.runtime_binding_id}; allowed={ops} (fail-closed)"
        )

    return candidate
