"""Production governance DB path resolution for the Hermes runtime.

This module is the single, auditable place that decides WHERE the authoritative
Hermes governance SQLite database lives at runtime. It encodes the approved
Phase 6 §27 / Runtime-Integration decision:

    HERMES_GOVERNANCE_DB          (explicit override, wins)
            ↓ if unset
    %LOCALAPPDATA%\\Hermes\\governance.db   (default production location)

Rules (enforced here, not elsewhere):
- repository / worktree paths are NEVER used as the production location
- the resolver has NO filesystem side effect (it does not create directories
  or files; bootstrap does that, only when opening the runtime store)
- empty / whitespace / relative overrides are rejected by explicit policy
- a missing LOCALAPPDATA on the default path fails closed with a clear error
- the governance DB is runtime state and must never be committed

Phase 6 boundary preserved: this module only resolves a path. It grants no
execution authority and invokes no worker.
"""

from __future__ import annotations

import os
from pathlib import Path


class GovernanceRuntimeConfigError(RuntimeError):
    """Raised when the governance DB path cannot be resolved safely."""


def _resolve_localappdata(env: dict[str, str] | None = None) -> Path:
    """Return the platform-local application-data directory, or raise.

    Only the Windows ``LOCALAPPDATA`` variable is consulted, matching the
    approved production location. A missing value fails closed rather than
    falling back to the current working directory.
    """
    env = os.environ if env is None else env
    value = env.get("LOCALAPPDATA")
    if not value or not value.strip():
        raise GovernanceRuntimeConfigError(
            "LOCALAPPDATA is not set; cannot resolve the default governance "
            "database location. Set HERMES_GOVERNANCE_DB explicitly or ensure "
            "LOCALAPPDATA is available."
        )
    return Path(value)


def resolve_governance_db_path(
    env: dict[str, str] | None = None,
    *,
    require_absolute: bool = True,
) -> Path:
    """Resolve the authoritative governance DB path.

    Resolution order:
        1. HERMES_GOVERNANCE_DB if explicitly set (absolute, non-empty)
        2. %LOCALAPPDATA%\\Hermes\\governance.db

    Args:
        env: optional mapping overriding ``os.environ`` (used by tests).
        require_absolute: if True (default), reject relative override values.

    Returns:
        An absolute :class:`pathlib.Path`. The resolver performs no filesystem
        writes; the parent directory is created only when the runtime store is
        opened.

    Raises:
        GovernanceRuntimeConfigError: on empty/whitespace/relative override, or
            a missing LOCALAPPDATA for the default path.
    """
    env = os.environ if env is None else env

    override = env.get("HERMES_GOVERNANCE_DB")
    if override is not None and override.strip():
        candidate = Path(override.strip())
        if require_absolute and not candidate.is_absolute():
            raise GovernanceRuntimeConfigError(
                f"HERMES_GOVERNANCE_DB override must be an absolute path, "
                f"got relative: {override!r}"
            )
        return candidate.resolve()

    localappdata = _resolve_localappdata(env)
    return (localappdata / "Hermes" / "governance.db").resolve()


def default_governance_db_path(env: dict[str, str] | None = None) -> Path:
    """Return only the default production path (no override consulted)."""
    return (_resolve_localappdata(env) / "Hermes" / "governance.db").resolve()
