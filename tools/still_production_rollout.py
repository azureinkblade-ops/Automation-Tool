# -*- coding: utf-8 -*-
"""Thin transactional coordinator over V2 and Promo Master bounded rollouts.

COORDINATION != AUTHORITY. No third call budget. No per-call admission.
"""
from __future__ import annotations

import re
import threading
from typing import Any, Dict, FrozenSet, List, Tuple

from promo_copy import story_key
from tools.promo_master_activation import (
    get_bounded_promo_master_rollout_status,
    start_bounded_promo_master_rollout,
    stop_bounded_promo_master_rollout,
)
from tools.still_v2_activation import (
    get_bounded_still_v2_rollout_status,
    rollout_client_allowed,
    start_bounded_still_v2_rollout,
    stop_bounded_still_v2_rollout,
)

COORDINATOR_NOVELS: FrozenSet[str] = frozenset({"EN", "HA", "HP"})
COORDINATOR_SEAMS: FrozenSet[str] = frozenset({"comment-content", "resurfacing"})
COORDINATOR_MAX_CALLS = 3
START_ORDER: Tuple[str, ...] = ("v2", "pm")

_lock = threading.Lock()


class DualRolloutError(ValueError):
    """Rejected dual-rollout coordinator input or state."""


def _parse_novels(novels: Any) -> FrozenSet[str]:
    if isinstance(novels, str):
        parts = [p for p in re.split(r"[\s,]+", novels.strip()) if p]
    elif isinstance(novels, (list, tuple, set, frozenset)):
        parts = [str(p).strip() for p in novels if str(p).strip()]
    else:
        raise DualRolloutError("novels must be a string or sequence")
    if not parts:
        raise DualRolloutError("novels empty")
    out = set()
    for part in parts:
        abbr = story_key(part)
        if not abbr:
            raise DualRolloutError(f"unknown novel: {part}")
        if abbr not in COORDINATOR_NOVELS:
            raise DualRolloutError(f"novel outside coordinator envelope: {abbr}")
        out.add(abbr)
    return frozenset(out)


def _parse_seams(seams: Any) -> FrozenSet[str]:
    if isinstance(seams, str):
        parts = [p for p in re.split(r"[\s,]+", seams.strip()) if p]
    elif isinstance(seams, (list, tuple, set, frozenset)):
        parts = [str(p).strip() for p in seams if str(p).strip()]
    else:
        raise DualRolloutError("seams must be a string or sequence")
    if not parts:
        raise DualRolloutError("seams empty")
    out = set()
    for part in parts:
        sid = str(part).strip().lower()
        if sid not in COORDINATOR_SEAMS:
            raise DualRolloutError(f"seam outside coordinator envelope: {part}")
        out.add(sid)
    return frozenset(out)


def _parse_max_calls(max_calls: Any) -> int:
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls <= 0:
        raise DualRolloutError("max_calls must be a positive int")
    if max_calls > COORDINATOR_MAX_CALLS:
        raise DualRolloutError("max_calls exceeds authorized envelope")
    return int(max_calls)


def _alignment(v2: Dict[str, Any], pm: Dict[str, Any]) -> str:
    if not v2.get("active") and not pm.get("active"):
        return "both_inactive"
    if v2.get("active") and not pm.get("active"):
        return "v2_active_only"
    if pm.get("active") and not v2.get("active"):
        return "pm_active_only"
    if (
        tuple(v2.get("novels") or ()) == tuple(pm.get("novels") or ())
        and tuple(v2.get("seams") or ()) == tuple(pm.get("seams") or ())
        and v2.get("max_calls") == pm.get("max_calls")
    ):
        return "both_active_aligned"
    return "both_active_mismatched"


def still_production_rollout_status() -> Dict[str, Any]:
    v2 = get_bounded_still_v2_rollout_status()
    pm = get_bounded_promo_master_rollout_status()
    state = _alignment(v2, pm)
    return {
        "active": bool(v2.get("active") and pm.get("active")),
        "aligned": state == "both_active_aligned",
        "state": state,
        "v2": v2,
        "promo_master": pm,
    }


def start_still_production_rollout(novels: Any, seams: Any, max_calls: Any) -> Dict[str, Any]:
    nset = _parse_novels(novels)
    sset = _parse_seams(seams)
    nmax = _parse_max_calls(max_calls)
    novels_arg = ",".join(sorted(nset))
    seams_arg = ",".join(sorted(sset))
    starters = {
        "v2": lambda: start_bounded_still_v2_rollout(novels_arg, seams_arg, nmax),
        "pm": lambda: start_bounded_promo_master_rollout(novels_arg, seams_arg, nmax),
    }
    stoppers = {
        "v2": stop_bounded_still_v2_rollout,
        "pm": stop_bounded_promo_master_rollout,
    }
    with _lock:
        v2 = get_bounded_still_v2_rollout_status()
        pm = get_bounded_promo_master_rollout_status()
        if v2.get("active"):
            raise DualRolloutError("preexisting V2 rollout is active")
        if pm.get("active"):
            raise DualRolloutError("preexisting Promo Master rollout is active")
        started: List[str] = []
        try:
            for key in START_ORDER:
                starters[key]()
                started.append(key)
        except Exception as exc:
            for key in reversed(started):
                try:
                    stoppers[key]()
                except Exception:
                    pass
            raise DualRolloutError(f"dual start failed: {exc}") from exc
    return still_production_rollout_status()


def stop_still_production_rollout() -> Dict[str, Any]:
    errors: Dict[str, str] = {}
    with _lock:
        try:
            stop_bounded_still_v2_rollout()
        except Exception as exc:
            errors["v2"] = str(exc)
        try:
            stop_bounded_promo_master_rollout()
        except Exception as exc:
            errors["promo_master"] = str(exc)
    st = still_production_rollout_status()
    st["stop_errors"] = errors
    st["both_stopped"] = (not st["v2"].get("active")) and (not st["promo_master"].get("active"))
    return st


def handle_still_production_rollout_http(
    method: str, path: str, body: Any, client_host: str
) -> tuple[int, Dict[str, Any]]:
    if not rollout_client_allowed(client_host):
        return 403, {"ok": False, "error": "loopback only"}
    payload = body if isinstance(body, dict) else {}
    verb = str(method or "").upper()
    route = str(path or "").split("?", 1)[0]
    try:
        if verb == "GET" and route == "/api/still-production-rollout-status":
            st = still_production_rollout_status()
            return 200, {"ok": True, **st}
        if verb == "POST" and route == "/api/still-production-rollout-start":
            st = start_still_production_rollout(
                payload.get("novels"),
                payload.get("seams"),
                payload.get("max_calls"),
            )
            return 200, {"ok": True, **st}
        if verb == "POST" and route == "/api/still-production-rollout-stop":
            st = stop_still_production_rollout()
            code = 200 if st.get("both_stopped") else 409
            return code, {"ok": bool(st.get("both_stopped")), **st}
        return 404, {"ok": False, "error": "unknown dual rollout route"}
    except DualRolloutError as exc:
        return 400, {"ok": False, "error": str(exc)}
