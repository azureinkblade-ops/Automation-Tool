"""EA-4D.3E-A: trusted local-worker launch configuration types + validation.

This module defines the immutable, deterministically-hashable configuration for
the ``LOCAL_WORKER_ADAPTER`` real-runtime boundary. It contains NO execution
logic and creates NO process. It is the data/validation half of EA-4D.3E-A/B;
the process-invocation half (3E-C) is separately authorized and not present
here.

Design (frozen by the EA-4D.3E design packet):
    - configuration is symbolic and resolves through trusted static/versioned
      configuration (no PATH discovery, no task-controlled executable);
    - the canonical config hash MUST equal ``WorkerRuntimeBinding.configuration_hash``;
    - resolution is exact: no fallback, no nearest-version, no implicit upgrade;
    - the resolved configuration fully determines the process boundary
      (executable, argv structure, cwd, environment allowlist), with NO
      task-controlled command structure.

Controlling invariant (frozen):
    LAUNCH_ATTEMPT_RECORDED != WORKER STARTED
No ``ExecutionStartResult`` and no ``EXECUTING`` are introduced here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from tools.hermes_core.execution_start import WorkerRuntimeBinding


# --------------------------------------------------------------------------- #
# Errors (narrowly scoped; frozen domain hierarchies untouched)
# --------------------------------------------------------------------------- #
class LocalWorkerConfigError(Exception):
    """Base error for EA-4D.3E local-worker configuration resolution."""


class LocalWorkerConfigMissingError(LocalWorkerConfigError):
    """Trusted config id not present in the registry (fail closed)."""


class LocalWorkerConfigHashMismatchError(LocalWorkerConfigError):
    """Resolved config hash does not equal the binding snapshot hash."""


class LocalWorkerConfigValidationError(LocalWorkerConfigError):
    """Config itself is invalid (e.g. non-absolute executable)."""


# --------------------------------------------------------------------------- #
# Immutable, deterministically-hashable configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LocalWorkerLaunchConfig:
    """Trusted, immutable launch configuration for one LOCAL_WORKER_ADAPTER.

    Every field that influences the process boundary is fixed here. Task/request
    input may contribute only DATA values into explicitly permitted request
    fields, never into executable/interpreter/argv-structure/cwd/environment/
    adapter-selection/config-version.
    """

    config_id: str
    config_version: str
    executable: str                      # absolute trusted path
    argv_template: Tuple[str, ...]       # trusted structure; NO task control
    cwd: Optional[str] = None            # absolute trusted path, or None
    environment_allowlist: Tuple[str, ...] = field(default_factory=tuple)
    acknowledgement_mode: str = "hermes-local-worker-v1"
    lookup_mode: str = "hermes-local-worker-v1"

    def __post_init__(self) -> None:
        if not self.executable or not self._is_absolute(self.executable):
            raise LocalWorkerConfigValidationError(
                "executable must be an absolute trusted path; "
                f"got {self.executable!r}")
        if self.cwd is not None and not self._is_absolute(self.cwd):
            raise LocalWorkerConfigValidationError(
                "cwd must be an absolute trusted path or None; "
                f"got {self.cwd!r}")

    @staticmethod
    def _is_absolute(path: str) -> bool:
        # Windows + POSIX: only a rooted path with a drive/root qualifies as
        # trusted (no relative path, no bare name subject to PATH discovery).
        if not path:
            return False
        if path.startswith("/") or path.startswith("\\"):
            return True
        # Windows drive root, e.g. C:\ or C:/
        if len(path) >= 2 and path[1] == ":" and (path[2:3] in ("/", "\\", "")):
            return True
        return False


def local_worker_config_canonical_hash(config: LocalWorkerLaunchConfig) -> str:
    """Deterministic SHA-256 over the configuration's boundary-determining fields.

    Must equal ``WorkerRuntimeBinding.configuration_hash`` for the binding that
    references this config. Stable across process invocations (sorted keys,
    no volatile fields).
    """
    material = {
        "config_id": config.config_id,
        "config_version": config.config_version,
        "executable": config.executable,
        "argv_template": list(config.argv_template),
        "cwd": config.cwd,
        "environment_allowlist": list(config.environment_allowlist),
        "acknowledgement_mode": config.acknowledgement_mode,
        "lookup_mode": config.lookup_mode,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Trusted static configuration registry
# --------------------------------------------------------------------------- #
class TrustedLocalWorkerConfigRegistry:
    """In-process trusted registry for EA-4D.3E-A/B.

    Models the frozen "trusted static/versioned configuration" source. Exact
    identity resolution only: a config is addressed by ``config_id``; there is
    no nearest-version fallback. The authoritative deployment-backed source is
    frozen for a later phase and is not required for the no-spawn slice.
    """

    def __init__(self, configs: Optional[Dict[str, LocalWorkerLaunchConfig]] = None) -> None:
        self._configs: Dict[str, LocalWorkerLaunchConfig] = dict(configs or {})

    def register(self, config: LocalWorkerLaunchConfig) -> None:
        self._configs[config.config_id] = config

    def resolve(
        self,
        binding: WorkerRuntimeBinding,
    ) -> LocalWorkerLaunchConfig:
        """Resolve the trusted config referenced by a frozen binding snapshot.

        Fail-closed on missing config or configuration_hash mismatch. Never
        performs version fallback.
        """
        config_id = binding.configuration_reference
        config = self._configs.get(config_id)
        if config is None:
            raise LocalWorkerConfigMissingError(
                f"trusted local-worker config {config_id!r} not found; "
                f"no fallback permitted")
        derived = local_worker_config_canonical_hash(config)
        if derived != binding.configuration_hash:
            raise LocalWorkerConfigHashMismatchError(
                f"config {config_id!r} hash {derived} does not match binding "
                f"configuration_hash {binding.configuration_hash}; fail closed")
        return config
