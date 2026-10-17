# -*- coding: utf-8 -*-
"""Process-local bounded Promo Master default rollout (CPU). Independent of V2."""
from __future__ import annotations

import os
import re
import threading
from typing import Any, Dict, FrozenSet, Optional

from promo_copy import story_key

CANONICAL_SEAMS: FrozenSet[str] = frozenset(
    {
        "weekday",
        "chapter-release",
        "resurfacing",
        "comment-content",
        "arc-campaign",
        "experiment-social-pack",
    }
)
AUTHORIZED_ROLLOUT_NOVELS: FrozenSet[str] = frozenset({"EN", "HA", "HP"})
AUTHORIZED_ROLLOUT_SEAMS: FrozenSet[str] = CANONICAL_SEAMS
AUTHORIZED_ROLLOUT_MAX_CALLS = 3

_lock = threading.Lock()
_budget: Optional[Dict[str, int]] = None
_session: Optional[Dict[str, FrozenSet[str]]] = None


class BoundedPromoMasterRolloutError(ValueError):
    """Rejected bounded Promo Master start/stop input or state."""


def _canonical_novel(novel: Any) -> str:
    if novel is None:
        return ""
    return story_key(str(novel))


def _canonical_seam(seam: Any) -> str:
    if seam is None:
        return ""
    token = str(seam).strip().lower()
    return token if token in CANONICAL_SEAMS else ""


def _parse_novels(novels: Any) -> FrozenSet[str]:
    if isinstance(novels, str):
        parts = [p for p in re.split(r"[\s,]+", novels.strip()) if p]
    elif isinstance(novels, (list, tuple, set, frozenset)):
        parts = [str(p).strip() for p in novels if str(p).strip()]
    else:
        raise BoundedPromoMasterRolloutError("novels must be a string or sequence")
    if not parts:
        raise BoundedPromoMasterRolloutError("novels empty")
    out = set()
    for part in parts:
        abbr = story_key(part)
        if not abbr:
            raise BoundedPromoMasterRolloutError(f"unknown novel: {part}")
        if abbr not in AUTHORIZED_ROLLOUT_NOVELS:
            raise BoundedPromoMasterRolloutError(f"novel outside authorized envelope: {abbr}")
        out.add(abbr)
    return frozenset(out)


def _parse_seams(seams: Any) -> FrozenSet[str]:
    if isinstance(seams, str):
        parts = [p for p in re.split(r"[\s,]+", seams.strip()) if p]
    elif isinstance(seams, (list, tuple, set, frozenset)):
        parts = [str(p).strip() for p in seams if str(p).strip()]
    else:
        raise BoundedPromoMasterRolloutError("seams must be a string or sequence")
    if not parts:
        raise BoundedPromoMasterRolloutError("seams empty")
    out = set()
    for part in parts:
        sid = _canonical_seam(part)
        if not sid:
            raise BoundedPromoMasterRolloutError(f"unknown seam: {part}")
        if sid not in AUTHORIZED_ROLLOUT_SEAMS:
            raise BoundedPromoMasterRolloutError(f"seam outside authorized envelope: {sid}")
        out.add(sid)
    return frozenset(out)


def begin_promo_master_default_rollout(
    max_calls: int,
    novels: Any = None,
    seams: Any = None,
) -> Dict[str, Any]:
    """Administrative begin. Resets consumed. max_calls=0 allowed."""
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 0:
        raise BoundedPromoMasterRolloutError("max_calls must be a non-negative int")
    nset = _parse_novels(novels if novels is not None else "EN,HA,HP")
    sset = _parse_seams(seams if seams is not None else ",".join(sorted(CANONICAL_SEAMS)))
    global _budget, _session
    with _lock:
        _session = {"novels": nset, "seams": sset}
        _budget = {"max_calls": int(max_calls), "consumed_calls": 0}
    return promo_master_default_rollout_status()


def end_promo_master_default_rollout() -> None:
    global _budget, _session
    with _lock:
        _budget = None
        _session = None


def start_bounded_promo_master_rollout(novels: Any, seams: Any, max_calls: int) -> Dict[str, Any]:
    """Start omitted-PM session in THIS process. Second start rejected."""
    nset = _parse_novels(novels)
    sset = _parse_seams(seams)
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls <= 0:
        raise BoundedPromoMasterRolloutError("max_calls must be a positive int")
    if max_calls > AUTHORIZED_ROLLOUT_MAX_CALLS:
        raise BoundedPromoMasterRolloutError("max_calls exceeds authorized envelope")
    global _session, _budget
    with _lock:
        if _session is not None:
            raise BoundedPromoMasterRolloutError("rollout already active")
        _session = {"novels": nset, "seams": sset}
        _budget = {"max_calls": int(max_calls), "consumed_calls": 0}
    return get_bounded_promo_master_rollout_status()


def stop_bounded_promo_master_rollout() -> Dict[str, Any]:
    end_promo_master_default_rollout()
    return get_bounded_promo_master_rollout_status()


def get_bounded_promo_master_rollout_status() -> Dict[str, Any]:
    with _lock:
        if _session is None:
            return {
                "active": False,
                "novels": None,
                "seams": None,
                "max_calls": None if _budget is None else _budget["max_calls"],
                "consumed_calls": 0 if _budget is None else _budget["consumed_calls"],
                "remaining_calls": None
                if _budget is None
                else _budget["max_calls"] - _budget["consumed_calls"],
                "budget_active": _budget is not None,
            }
        remaining = None if _budget is None else _budget["max_calls"] - _budget["consumed_calls"]
        return {
            "active": True,
            "novels": tuple(sorted(_session["novels"])),
            "seams": tuple(sorted(_session["seams"])),
            "max_calls": None if _budget is None else _budget["max_calls"],
            "consumed_calls": 0 if _budget is None else _budget["consumed_calls"],
            "remaining_calls": remaining,
            "budget_active": _budget is not None,
        }


def promo_master_default_rollout_status() -> Dict[str, Any]:
    return get_bounded_promo_master_rollout_status()


def remaining_promo_master_default_calls() -> Optional[int]:
    return get_bounded_promo_master_rollout_status()["remaining_calls"]


def reserve_promo_master_default_call() -> bool:
    global _budget
    with _lock:
        if _budget is None:
            return False
        if _budget["consumed_calls"] >= _budget["max_calls"]:
            return False
        _budget["consumed_calls"] += 1
        return True


def admit_omitted_promo_master(*, novel: Any = None, seam: Any = None) -> Dict[str, Any]:
    """Lock-protected omitted/default PM admission. Does not create V2 authority."""
    nid = _canonical_novel(novel)
    sid = _canonical_seam(seam)
    with _lock:
        if _session is None or _budget is None:
            return {"enabled": False, "source": "default"}
        novels = _session["novels"]
        seams = _session["seams"]
        if not (nid and nid in novels and sid and sid in seams):
            return {"enabled": False, "source": "scoped"}
        if _budget["consumed_calls"] >= _budget["max_calls"]:
            return {"enabled": False, "source": "budget"}
        _budget["consumed_calls"] += 1
        return {"enabled": True, "source": "bounded_rollout"}


def rollout_client_allowed(host: str) -> bool:
    return str(host or "").strip().lower() in {"127.0.0.1", "::1", "localhost"}


def handle_pm_rollout_http(method: str, path: str, body: Any, client_host: str) -> tuple[int, Dict[str, Any]]:
    if not rollout_client_allowed(client_host):
        return 403, {"ok": False, "error": "loopback only"}
    payload = body if isinstance(body, dict) else {}
    verb = str(method or "").upper()
    route = str(path or "").split("?", 1)[0]
    try:
        if verb == "GET" and route == "/api/promo-master-rollout-status":
            return 200, {"ok": True, **get_bounded_promo_master_rollout_status()}
        if verb == "POST" and route == "/api/promo-master-rollout-start":
            st = start_bounded_promo_master_rollout(
                payload.get("novels"),
                payload.get("seams"),
                payload.get("max_calls"),
            )
            return 200, {"ok": True, **st}
        if verb == "POST" and route == "/api/promo-master-rollout-stop":
            return 200, {"ok": True, **stop_bounded_promo_master_rollout()}
        if verb == "POST" and route == "/api/promo-master-rollout-decide":
            from tools.promo_master_production import resolve_activation

            decision = resolve_activation(
                explicit=None,
                novel=payload.get("novel"),
                seam=payload.get("seam"),
            )
            st = get_bounded_promo_master_rollout_status()
            return 200, {"ok": True, "decision": decision, "status": st}
        return 404, {"ok": False, "error": "unknown rollout route"}
    except BoundedPromoMasterRolloutError as exc:
        return 400, {"ok": False, "error": str(exc)}
