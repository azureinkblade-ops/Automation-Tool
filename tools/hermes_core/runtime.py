"""Runtime provider seam for the Hermes governance store.

This module is the ONE controlled place application/runtime code obtains the
authoritative governance store. It centralizes construction so that:

- the DB path comes from :mod:`tools.hermes_core.runtime_config`
- the schema catalog is loaded from the package's repository root (not cwd)
- the store is bootstrapped exactly once per process (application-lifetime)
- tests can override the DB path and reset the cached instance
- no caller constructs ``SQLiteGovernanceStore`` or ``sqlite3`` directly

Phase 6 boundary is preserved:
- the provider exposes only governance ACCEPTED state and integrity; it grants
  no execution authorization and invokes no worker.
- bootstrap fails closed on schema/version/integrity errors.

Connection ownership: application-lifetime (one store per process). The store
owns its single SQLite connection; call :func:`close_governance_store` at
process shutdown. The cached instance is reused across calls within a process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tools.hermes_core.governance_store import GovernanceStore
from tools.hermes_core.runtime_config import resolve_governance_db_path
from tools.hermes_core.schemas import load_schema_catalog
from tools.hermes_core.sqlite_governance_store import SQLiteGovernanceStore


# Module-level cached instance. This is the controlled singleton, not a raw
# global connection: only ``get_governance_store`` reads it, and ``reset_``/
# ``override`` seams exist for tests.
_cache: Optional[GovernanceStore] = None
_override_db_path: Optional[Path] = None


def _package_repo_root() -> Path:
    """Resolve the repository root that contains ``docs/architecture/schemas``.

    The schemas are loaded relative to the repo root, not ``Path.cwd()``, so
    the provider works regardless of the process working directory.
    """
    # tools/hermes_core/runtime.py -> tools/hermes_core -> tools -> repo_root
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    return repo_root


def _build_store(db_path: Path) -> GovernanceStore:
    catalog = load_schema_catalog(_package_repo_root())
    store = SQLiteGovernanceStore(db_path, catalog)
    # Ensure the parent directory exists only at open time (no side effect
    # during path resolution). tolerate_missing_parent keeps this explicit.
    return store


def get_governance_store() -> GovernanceStore:
    """Return the process-wide governance store, constructing it on first use.

    The DB path resolves via :func:`resolve_governance_db_path` unless a test
    override is active. Bootstrap (schema v1, version assert) happens inside
    ``SQLiteGovernanceStore.__init__``; any failure propagates as a
    ``GovernanceStoreError`` (fail-closed).

    Returns:
        A :class:`GovernanceStore` (the abstract type the app should depend on).
    """
    global _cache
    if _cache is not None:
        return _cache
    db_path = _override_db_path or resolve_governance_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _cache = _build_store(db_path)
    return _cache


def close_governance_store() -> None:
    """Close the cached store and release the connection, if open."""
    global _cache
    if _cache is not None:
        try:
            _cache.close()
        finally:
            _cache = None


def reset_governance_store_cache() -> None:
    """Drop the cached instance WITHOUT closing (for test isolation).

    Tests that set an override should call this to ensure the next
    ``get_governance_store`` rebuilds against the override. Callers that want a
    clean shutdown should use :func:`close_governance_store` first.
    """
    global _cache
    _cache = None


# -- test seams ---------------------------------------------------------------

def set_governance_db_path_override(path: Optional[Path]) -> None:
    """Override the DB path for tests. Pass ``None`` to clear.

    This must be paired with :func:`reset_governance_store_cache` so the next
    call rebuilds against the override. It does not touch production config.
    """
    global _override_db_path
    _override_db_path = Path(path) if path is not None else None
    reset_governance_store_cache()


# -- runtime query surface ---------------------------------------------------
# These helpers answer governance questions only. They never transition state,
# never authorize execution, and never invoke a worker.

def get_governance_chain(task_id: str) -> object:
    """Load the persisted governance chain for a task (or raise if absent)."""
    return get_governance_store().load_task_governance_chain(task_id)


def get_governance_state(task_id: str) -> Optional[str]:
    """Return the current governance state for a task, or ``None`` if none."""
    try:
        chain = get_governance_store().load_task_governance_chain(task_id)
    except Exception:
        # Missing task / no persisted governance is an explicit, non-fatal state.
        return None
    return chain.governance_state


def verify_governance_integrity(task_id: Optional[str] = None) -> object:
    """Verify ledger/store integrity. Full-store verification when unspecified."""
    return get_governance_store().verify_integrity()


def is_governance_accepted(task_id: str) -> bool:
    """True only if the task's governance state is ``ACCEPTED``.

    ``ACCEPTED`` is governance acceptance ONLY. It does not imply, create, or
    authorize execution.
    """
    return get_governance_state(task_id) == "ACCEPTED"


# ---------------------------------------------------------------------------
# Execution-authority provider seam (EA-2)
# ---------------------------------------------------------------------------
# This mirrors the governance provider but for the SEPARATE execution-authority
# store. It returns the store only; it never authorizes, issues, claims, or
# executes. The store persists EA-1 immutable representations and verifies their
# integrity. ACCEPTED != EXECUTION AUTHORIZATION is preserved: the provider owns
# no execution authority.

_authority_cache: Optional["ExecutionAuthorizationStore"] = None
_authority_override_db_path: Optional[Path] = None


def _build_authority_store(db_path: Path) -> "ExecutionAuthorizationStore":
    from tools.hermes_core.sqlite_execution_authorization_store import (
        SQLiteExecutionAuthorizationStore,
    )

    return SQLiteExecutionAuthorizationStore(db_path)


def get_execution_authorization_store() -> "ExecutionAuthorizationStore":
    """Return the process-wide execution-authority store.

    DB path resolves via :func:`resolve_execution_authority_db_path` unless a
    test override is active. Bootstrap (schema v1, version assert, integrity
    guard) happens inside ``SQLiteExecutionAuthorizationStore.__init__``; any
    failure propagates as an ``ExecutionAuthorizationStoreError`` (fail-closed).

    The returned store only persists/verifies EA-1 artifacts. It grants no
    execution authority and invokes no worker.
    """
    global _authority_cache
    if _authority_cache is not None:
        return _authority_cache
    from tools.hermes_core.runtime_config import resolve_execution_authority_db_path

    db_path = _authority_override_db_path or resolve_execution_authority_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _authority_cache = _build_authority_store(db_path)
    return _authority_cache


def close_execution_authorization_store() -> None:
    """Close the cached authority store and release the connection, if open."""
    global _authority_cache
    if _authority_cache is not None:
        try:
            _authority_cache.close()
        finally:
            _authority_cache = None


def reset_execution_authorization_store_cache() -> None:
    """Drop the cached authority instance WITHOUT closing (test isolation)."""
    global _authority_cache
    _authority_cache = None


def set_execution_authority_db_path_override(path: Optional[Path]) -> None:
    """Override the authority DB path for tests. Pass ``None`` to clear."""
    global _authority_override_db_path
    _authority_override_db_path = Path(path) if path is not None else None
    reset_execution_authorization_store_cache()
