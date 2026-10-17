"""Still-caller V2 default activation (CPU). Separate from profile availability.

image_pipeline_v2_activation.json remains PROFILE AVAILABILITY only.
This resolver answers whether an ordinary still caller should request V2.

Precedence:
  explicit True/False
  -> STILL_V2_ENABLED (global gate)
  -> STILL_V2_NOVELS allowlist
  -> STILL_V2_SEAMS allowlist
  -> active default-call budget
  -> OFF

STILL_V2_ENABLED unset/OFF -> omitted calls OFF, allowlists ignored.
STILL_V2_ENABLED=1 and either allowlist unset/empty -> omitted calls OFF.
Eligible omitted V2 also requires begin_still_v2_default_rollout().
Unknown allowlist tokens are ignored (fail-closed).
Read on each call. No restart. Does not touch Comic or photorealistic.
"""
from __future__ import annotations

import contextlib
import os
import re
import threading
from typing import Any, Dict, FrozenSet, Iterator, Optional

from promo_copy import story_key

ENV_FLAG = "STILL_V2_ENABLED"
ENV_NOVELS = "STILL_V2_NOVELS"
ENV_SEAMS = "STILL_V2_SEAMS"

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

_tls = threading.local()
_budget_lock = threading.Lock()
_budget: Optional[Dict[str, int]] = None
_session: Optional[Dict[str, FrozenSet[str]]] = None

AUTHORIZED_ROLLOUT_NOVELS: FrozenSet[str] = frozenset({"EN", "HA", "HP"})
AUTHORIZED_ROLLOUT_SEAMS: FrozenSet[str] = frozenset({"comment-content", "resurfacing"})
AUTHORIZED_ROLLOUT_MAX_CALLS = 3


class BoundedStillV2RolloutError(ValueError):
    """Rejected bounded-rollout start/stop input or state."""


def _flag_on(raw: Any) -> bool:
    return str(raw if raw is not None else "").strip().lower() not in {
        "",
        "0",
        "false",
        "no",
        "off",
    }


def persistent_enabled(*, environ: Optional[Dict[str, str]] = None) -> bool:
    env = environ if environ is not None else os.environ
    return _flag_on(env.get(ENV_FLAG))


def parse_still_v2_novels(raw: Any) -> FrozenSet[str]:
    """Comma or whitespace list. Canonical abbrs only. Unknown tokens dropped."""
    text = str(raw if raw is not None else "").strip()
    if not text:
        return frozenset()
    out = set()
    for part in re.split(r"[\s,]+", text):
        token = part.strip()
        if not token:
            continue
        abbr = story_key(token)
        if abbr:
            out.add(abbr)
    return frozenset(out)


def parse_still_v2_seams(raw: Any) -> FrozenSet[str]:
    """Comma or whitespace list. Canonical seam IDs only. Unknown tokens dropped."""
    text = str(raw if raw is not None else "").strip()
    if not text:
        return frozenset()
    out = set()
    for part in re.split(r"[\s,]+", text):
        token = part.strip().lower()
        if token in CANONICAL_SEAMS:
            out.add(token)
    return frozenset(out)


def novels_allowlist(*, environ: Optional[Dict[str, str]] = None) -> FrozenSet[str]:
    ov = getattr(_tls, "novels_override", None)
    if ov is not None:
        return parse_still_v2_novels(ov)
    env = environ if environ is not None else os.environ
    return parse_still_v2_novels(env.get(ENV_NOVELS))


def seams_allowlist(*, environ: Optional[Dict[str, str]] = None) -> FrozenSet[str]:
    ov = getattr(_tls, "seams_override", None)
    if ov is not None:
        return parse_still_v2_seams(ov)
    env = environ if environ is not None else os.environ
    return parse_still_v2_seams(env.get(ENV_SEAMS))


def _override() -> Optional[bool]:
    return getattr(_tls, "override", None)


def _canonical_novel(novel: Any) -> str:
    if novel is None:
        return ""
    return story_key(str(novel))


def _canonical_seam(seam: Any) -> str:
    if seam is None:
        return ""
    token = str(seam).strip().lower()
    if token in CANONICAL_SEAMS:
        return token
    return ""


def begin_still_v2_default_rollout(max_calls: int) -> Dict[str, Any]:
    """Process-local omitted-V2 budget. Explicit True/False do not use this.

    max_calls=0: active with zero slots (all omitted V2 OFF).
    negative or non-int (including bool): ValueError, fail-closed, no start.
    A second begin resets consumed to 0.
    """
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 0:
        raise ValueError("max_calls must be a non-negative int")
    global _budget
    with _budget_lock:
        _budget = {"max_calls": int(max_calls), "consumed_calls": 0}
    return still_v2_default_rollout_status()


def end_still_v2_default_rollout() -> None:
    global _budget
    with _budget_lock:
        _budget = None


def still_v2_default_rollout_status() -> Dict[str, Any]:
    with _budget_lock:
        if _budget is None:
            return {
                "active": False,
                "max_calls": None,
                "consumed_calls": 0,
                "remaining_calls": None,
            }
        remaining = _budget["max_calls"] - _budget["consumed_calls"]
        return {
            "active": True,
            "max_calls": _budget["max_calls"],
            "consumed_calls": _budget["consumed_calls"],
            "remaining_calls": remaining,
        }


def remaining_still_v2_default_calls() -> Optional[int]:
    return still_v2_default_rollout_status()["remaining_calls"]


def _parse_authorized_novels(novels: Any) -> FrozenSet[str]:
    if isinstance(novels, str):
        parts = [p for p in re.split(r"[\s,]+", novels.strip()) if p]
    elif isinstance(novels, (list, tuple, set, frozenset)):
        parts = [str(p).strip() for p in novels if str(p).strip()]
    else:
        raise BoundedStillV2RolloutError("novels must be a string or sequence")
    if not parts:
        raise BoundedStillV2RolloutError("novels empty")
    out = set()
    for part in parts:
        abbr = story_key(part)
        if not abbr:
            raise BoundedStillV2RolloutError(f"unknown novel: {part}")
        if abbr not in AUTHORIZED_ROLLOUT_NOVELS:
            raise BoundedStillV2RolloutError(f"novel outside authorized envelope: {abbr}")
        out.add(abbr)
    return frozenset(out)


def _parse_authorized_seams(seams: Any) -> FrozenSet[str]:
    if isinstance(seams, str):
        parts = [p for p in re.split(r"[\s,]+", seams.strip()) if p]
    elif isinstance(seams, (list, tuple, set, frozenset)):
        parts = [str(p).strip() for p in seams if str(p).strip()]
    else:
        raise BoundedStillV2RolloutError("seams must be a string or sequence")
    if not parts:
        raise BoundedStillV2RolloutError("seams empty")
    out = set()
    for part in parts:
        sid = _canonical_seam(part)
        if not sid:
            raise BoundedStillV2RolloutError(f"unknown seam: {part}")
        if sid not in AUTHORIZED_ROLLOUT_SEAMS:
            raise BoundedStillV2RolloutError(f"seam outside authorized envelope: {sid}")
        out.add(sid)
    return frozenset(out)


def start_bounded_still_v2_rollout(
    novels: Any,
    seams: Any,
    max_calls: int,
) -> Dict[str, Any]:
    """Start omitted-V2 session in THIS process. Does not mutate os.environ.

    Envelope: novels subset of EN,HA,HP; seams subset of
    comment-content,resurfacing; 1 <= max_calls <= 3.
    Rejects a second start while active (does not reset budget).
    """
    nset = _parse_authorized_novels(novels)
    sset = _parse_authorized_seams(seams)
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls <= 0:
        raise BoundedStillV2RolloutError("max_calls must be a positive int")
    if max_calls > AUTHORIZED_ROLLOUT_MAX_CALLS:
        raise BoundedStillV2RolloutError("max_calls exceeds authorized envelope")
    global _session, _budget
    with _budget_lock:
        if _session is not None:
            raise BoundedStillV2RolloutError("rollout already active")
        _session = {"novels": nset, "seams": sset}
        _budget = {"max_calls": int(max_calls), "consumed_calls": 0}
    return get_bounded_still_v2_rollout_status()


def stop_bounded_still_v2_rollout() -> Dict[str, Any]:
    global _session, _budget
    with _budget_lock:
        _session = None
        _budget = None
    return get_bounded_still_v2_rollout_status()


def get_bounded_still_v2_rollout_status() -> Dict[str, Any]:
    with _budget_lock:
        if _session is None:
            budget_active = _budget is not None
            remaining = None
            consumed = 0
            max_calls = None
            if _budget is not None:
                max_calls = _budget["max_calls"]
                consumed = _budget["consumed_calls"]
                remaining = max_calls - consumed
            return {
                "active": False,
                "novels": None,
                "seams": None,
                "max_calls": max_calls if budget_active else None,
                "consumed_calls": consumed,
                "remaining_calls": remaining,
                "budget_active": budget_active,
            }
        remaining = _budget["max_calls"] - _budget["consumed_calls"] if _budget else None
        return {
            "active": True,
            "novels": tuple(sorted(_session["novels"])),
            "seams": tuple(sorted(_session["seams"])),
            "max_calls": None if _budget is None else _budget["max_calls"],
            "consumed_calls": 0 if _budget is None else _budget["consumed_calls"],
            "remaining_calls": remaining,
            "budget_active": _budget is not None,
        }


def rollout_client_allowed(host: str) -> bool:
    return str(host or "").strip().lower() in {"127.0.0.1", "::1", "localhost"}


def handle_rollout_http(method: str, path: str, body: Any, client_host: str) -> tuple[int, Dict[str, Any]]:
    """Loopback-only start/status/stop/decide. No image generation."""
    if not rollout_client_allowed(client_host):
        return 403, {"ok": False, "error": "loopback only"}
    payload = body if isinstance(body, dict) else {}
    verb = str(method or "").upper()
    route = str(path or "").split("?", 1)[0]
    try:
        if verb == "GET" and route == "/api/still-v2-rollout-status":
            st = get_bounded_still_v2_rollout_status()
            return 200, {"ok": True, **st}
        if verb == "POST" and route == "/api/still-v2-rollout-start":
            st = start_bounded_still_v2_rollout(
                payload.get("novels"),
                payload.get("seams"),
                payload.get("max_calls"),
            )
            return 200, {"ok": True, **st}
        if verb == "POST" and route == "/api/still-v2-rollout-stop":
            st = stop_bounded_still_v2_rollout()
            return 200, {"ok": True, **st}
        if verb == "POST" and route == "/api/still-v2-rollout-decide":
            decision = resolve_still_v2_enabled(
                None,
                novel=payload.get("novel"),
                seam=payload.get("seam"),
            )
            st = get_bounded_still_v2_rollout_status()
            return 200, {"ok": True, "decision": decision, "status": st}
        return 404, {"ok": False, "error": "unknown rollout route"}
    except BoundedStillV2RolloutError as exc:
        return 400, {"ok": False, "error": str(exc)}


def resolve_still_v2_enabled(
    explicit: Optional[bool] = None,
    *,
    novel: Any = None,
    seam: Any = None,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """explicit True/False -> session or env gates -> budget -> OFF."""
    if explicit is not None:
        return {"enabled": bool(explicit), "source": "explicit"}
    with _budget_lock:
        session = None if _session is None else {
            "novels": _session["novels"],
            "seams": _session["seams"],
        }
    if session is not None:
        global_on = True
        novels = session["novels"]
        seams = session["seams"]
    else:
        ov = _override()
        if ov is not None:
            global_on = bool(ov)
        else:
            global_on = persistent_enabled(environ=environ)
        if not global_on:
            return {"enabled": False, "source": "default"}
        novels = novels_allowlist(environ=environ)
        seams = seams_allowlist(environ=environ)
    nid = _canonical_novel(novel)
    sid = _canonical_seam(seam)
    if not (nid and nid in novels and sid and sid in seams):
        return {"enabled": False, "source": "scoped"}
    if not reserve_still_v2_default_call():
        return {"enabled": False, "source": "budget"}
    return {"enabled": True, "source": "scoped"}


def reserve_still_v2_default_call() -> bool:
    """Atomically consume one omitted-V2 slot. True if reserved."""
    global _budget
    with _budget_lock:
        if _budget is None:
            return False
        if _budget["consumed_calls"] >= _budget["max_calls"]:
            return False
        _budget["consumed_calls"] += 1
        return True


@contextlib.contextmanager
def still_v2_default_rollout(max_calls: int) -> Iterator[Dict[str, Any]]:
    """begin/end process-local omitted-V2 budget."""
    status = begin_still_v2_default_rollout(max_calls)
    try:
        yield status
    finally:
        end_still_v2_default_rollout()


@contextlib.contextmanager
def still_v2_default_override(
    enabled: bool,
    novels: Optional[str] = None,
    seams: Optional[str] = None,
) -> Iterator[None]:
    """Test-only thread-local still-caller default. Does not mutate os.environ.

    ``enabled`` simulates STILL_V2_ENABLED only. Novel and seam allowlists
    are separate; omit them to leave that dimension unset/empty.
    Omitted V2 still requires an active begin_still_v2_default_rollout().
    """
    prior = _override()
    had = hasattr(_tls, "override")
    prior_n = getattr(_tls, "novels_override", None)
    had_n = hasattr(_tls, "novels_override")
    prior_s = getattr(_tls, "seams_override", None)
    had_s = hasattr(_tls, "seams_override")
    _tls.override = bool(enabled)
    if novels is not None:
        _tls.novels_override = novels
    if seams is not None:
        _tls.seams_override = seams
    try:
        yield
    finally:
        if had:
            _tls.override = prior
        elif hasattr(_tls, "override"):
            delattr(_tls, "override")
        if novels is not None:
            if had_n:
                _tls.novels_override = prior_n
            elif hasattr(_tls, "novels_override"):
                delattr(_tls, "novels_override")
        if seams is not None:
            if had_s:
                _tls.seams_override = prior_s
            elif hasattr(_tls, "seams_override"):
                delattr(_tls, "seams_override")
