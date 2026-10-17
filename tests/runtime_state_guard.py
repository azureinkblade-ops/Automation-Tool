# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R3 — runtime state write barrier.

Protects production runtime state during pytest:
  growth-automation.json, automation_state.db (+WAL/SHM), social-posts,
  tiktok-posts, campaign metadata, chapter_assets, usage/rotation state.

Test writes are redirected to the isolation temp root. Resolving a protected
production path for write during tests aborts immediately.

Sentinel:
  RUNTIME_STATE_TEST_ISOLATION_INSTALLED=YES
  LIVE_RUNTIME_PATH_FALLBACK_ALLOWED=NO
  RUNTIME_STATE_GUARD_ACTIVE=YES
"""
from __future__ import annotations

import builtins
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

RUNTIME_STATE_TEST_ISOLATION_INSTALLED = False
LIVE_RUNTIME_PATH_FALLBACK_ALLOWED = False
_RUNTIME_STATE_GUARD_ACTIVE = False
_ABORT_ON_LIVE_WRITE = True
_ORIG_OPEN = None
_HIT_LOG: list[dict[str, Any]] = []

# Basename / relative path markers that must never be written under the live repo during tests.
_PROTECTED_BASENAMES = {
    "growth-automation.json",
    "automation_state.db",
    "automation_state.db-wal",
    "automation_state.db-shm",
    "kpi-sync-log.json",
    "promo-rotation.json",
    "usage-state.json",
}


def _log(rec: dict[str, Any]) -> None:
    _HIT_LOG.append(rec)
    out = os.environ.get("AT_RUNTIME_GUARD_OUT") or os.environ.get("R3_RUNTIME_GUARD_OUT")
    if not out:
        return
    try:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _iso_root() -> Optional[Path]:
    raw = os.environ.get("AT_TEST_ISOLATION_ROOT") or ""
    if not raw:
        return None
    try:
        return Path(raw).resolve()
    except Exception:
        return None


def _live_root() -> Path:
    # tests/ -> repo root
    return Path(__file__).resolve().parents[1]


def _is_live_protected_write(path: Path, mode: str) -> bool:
    writing = any(c in (mode or "r") for c in "wax+")
    if not writing:
        return False
    try:
        p = path.resolve()
    except Exception:
        p = path
    live = _live_root().resolve()
    name = p.name.lower()
    # Protected basenames under live root (not under at_iso_ temp)
    if "at_iso_" in str(p).lower():
        return False
    iso = _iso_root()
    if iso is not None:
        try:
            p.relative_to(iso)
            return False  # inside sandbox
        except Exception:
            pass
    try:
        p.relative_to(live)
    except Exception:
        return False  # outside live repo
    if name in {b.lower() for b in _PROTECTED_BASENAMES}:
        return True
    # Directory trees that must not receive new writes from tests
    parts_lower = {x.lower() for x in p.parts}
    for marker in ("social-posts", "tiktok-posts", "campaigns", "chapter_assets", "promo-image-archive"):
        if marker in parts_lower:
            # Allow reading; writing under these live dirs is blocked
            return True
    return False


class RuntimeStateGuardError(RuntimeError):
    """Abort when a test resolves a protected live runtime path for write."""


def _guarded_open(file, mode="r", *a, **k):  # type: ignore[no-untyped-def]
    try:
        path = Path(os.fspath(file))
    except TypeError:
        return _ORIG_OPEN(file, mode, *a, **k)
    if _is_live_protected_write(path, str(mode)):
        rec = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "action": "ABORT_LIVE_WRITE",
            "path": str(path),
            "mode": str(mode),
            "test": os.environ.get("PYTEST_CURRENT_TEST", ""),
        }
        _log(rec)
        if _ABORT_ON_LIVE_WRITE:
            raise RuntimeStateGuardError(
                f"R3_RUNTIME_STATE_GUARD: refused live write to protected path {path} "
                f"(LIVE_RUNTIME_PATH_FALLBACK_ALLOWED=NO)"
            )
    return _ORIG_OPEN(file, mode, *a, **k)


def redirect_growth_automation(app_mod: Any, sandbox: Path) -> None:
    """Point GROWTH_AUTOMATION_FILE at sandbox copy (never live)."""
    dest = sandbox / "growth-automation.json"
    if not dest.exists():
        # Start empty/schema-only — do NOT copy contaminated live state into tests as "truth"
        dest.write_text(
            json.dumps({"schemaVersion": 1, "resurfaced": {}, "r3_isolated": True}, indent=2),
            encoding="utf-8",
        )
    try:
        app_mod.GROWTH_AUTOMATION_FILE = dest
    except Exception:
        pass


def install_runtime_state_guard(*, sandbox: Optional[Path] = None) -> bool:
    global RUNTIME_STATE_TEST_ISOLATION_INSTALLED, _RUNTIME_STATE_GUARD_ACTIVE, _ORIG_OPEN
    if RUNTIME_STATE_TEST_ISOLATION_INSTALLED:
        return True
    if sandbox is None:
        sandbox = _iso_root()
    if sandbox is None:
        raise RuntimeError("runtime state guard requires AT_TEST_ISOLATION_ROOT")

    if _ORIG_OPEN is None:
        _ORIG_OPEN = builtins.open
        builtins.open = _guarded_open  # type: ignore[assignment]

    try:
        import app as app_mod
        redirect_growth_automation(app_mod, sandbox)
        # Also redirect common JSON state writers if present as Path constants
        for attr, name in (
            ("PROMO_ROTATION_FILE", "promo-rotation.json"),
            ("USAGE_STATE_FILE", "usage-state.json"),
        ):
            if hasattr(app_mod, attr):
                setattr(app_mod, attr, sandbox / name)
    except Exception:
        pass

    os.environ["AT_RUNTIME_STATE_GUARD"] = "1"
    RUNTIME_STATE_TEST_ISOLATION_INSTALLED = True
    _RUNTIME_STATE_GUARD_ACTIVE = True
    print("RUNTIME_STATE_TEST_ISOLATION_INSTALLED=YES", flush=True)
    print("LIVE_RUNTIME_PATH_FALLBACK_ALLOWED=NO", flush=True)
    print("RUNTIME_STATE_GUARD_ACTIVE=YES", flush=True)
    _log({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": "INSTALLED", "sandbox": str(sandbox)})
    return True


def runtime_state_guard_active() -> bool:
    return bool(_RUNTIME_STATE_GUARD_ACTIVE and RUNTIME_STATE_TEST_ISOLATION_INSTALLED)


def guard_hits() -> list[dict[str, Any]]:
    return list(_HIT_LOG)
