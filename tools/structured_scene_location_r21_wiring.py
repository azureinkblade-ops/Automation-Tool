# -*- coding: utf-8 -*-
"""R21_CORE_STRUCTURED_LOCATION_CUTOVER (thin live adapter; default OFF).

ENABLE_STRUCTURED_SCENE_LOCATION (env, default OFF) is the ONLY switch. It is not coupled to identity,
wardrobe, AIVSB, Visual Director or parser suppression.

Flag OFF: callers get their exact legacy kwargs back; this module never imports the frozen R21 core and never
opens the tag store or locations.yaml.
Flag ON: a still's location comes ONLY from a structured tag bound to the runtime beat text
(visual_sentences(chapter, 3, ...) of the same call), resolved through the frozen R21 core
(tools.structured_location_authority_r21: hash -> novel -> governed id -> same novel -> R12 role).
The legacy positive prose matcher is never consulted (locations=None). No tag -> no location (fail neutral).
The parser / suppression layer is never called (run_parser=False).
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

FLAG = "ENABLE_STRUCTURED_SCENE_LOCATION"
TAG_STORE_ENV = "STRUCTURED_SCENE_LOCATION_TAG_STORE"
STATS: Dict[str, int] = {"TAG_STORE_LOADS": 0, "LOCATIONS_LOADS": 0, "RESOLVES": 0, "BINDS": 0}
_JOB: Dict[str, Any] = {}
_SCOPE: "contextvars.ContextVar[Optional[Dict[str, Any]]]" = contextvars.ContextVar("r21_structured_beat_scope", default=None)
_DECISIONS: List[Dict[str, Any]] = []
NON_BEAT_ADDRESSABLE_LANES = frozenset({"VISUAL_DIRECTOR"})
MONITOR_LOG_ENV = "R21_JOB_MONITOR_LOG"
_DEFAULT_MONITOR_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "r21_job_monitoring.jsonl")
LAST_JOB_RECORD: Dict[str, Any] = {}


def enabled() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def _job() -> Dict[str, Any]:
    """Tag store + governed locations, loaded ONCE per job (process); reloaded only if a file changes."""
    from tools import structured_location_authority_r21 as core  # lazy: flag ON only
    path = os.environ.get(TAG_STORE_ENV, "")
    yaml_path = core.DEFAULT_LOCATIONS_YAML
    key = (path, os.path.getmtime(path) if path and os.path.exists(path) else None,
           os.path.getmtime(yaml_path) if os.path.exists(yaml_path) else None)
    if _JOB.get("key") != key:
        _JOB["tags"] = core.load_tag_store(path) if path else []
        STATS["TAG_STORE_LOADS"] += 1
        _JOB["governed"] = core.load_governed_locations(yaml_path)
        _JOB["yaml_sha"] = core._file_sha(yaml_path)  # provenance hash computed once per job, not per beat
        _JOB["store_sha"] = core._file_sha(path) if path else ""
        STATS["LOCATIONS_LOADS"] += 1
        _JOB["key"] = key
        _JOB["core"] = core
    return _JOB


@contextlib.contextmanager
def chapter_beat_scope(novel_id: str, runtime_beats: Sequence[str], chapter_id: str = ""):
    """Bind still index -> runtime beat identity for one chapter-still package (flag ON only)."""
    beats = [str(b) for b in runtime_beats]
    tok = _SCOPE.set({"NOVEL_ID": str(novel_id or "").upper(), "CHAPTER_ID": str(chapter_id or ""), "BEATS": beats,
                      "SHAS": [hashlib.sha256(b.encode("utf-8")).hexdigest() for b in beats], "DECIDED": {},
                      "STEP_MS": [], "STATS0": dict(STATS)})
    sc = _SCOPE.get()
    try:
        yield
    finally:
        _SCOPE.reset(tok)
        _emit_job_record(sc)


def _emit_job_record(sc: Dict[str, Any]) -> None:
    """R21 per-job monitoring record (observability only; never affects binding; never raises)."""
    try:
        decs = list(sc["DECIDED"].values())
        steps = sorted(sc["STEP_MS"])
        q = lambda f: round(steps[min(len(steps) - 1, max(0, int(round(f * len(steps))) - 1))], 4) if steps else None
        prov = [d.get("PROVENANCE") or {} for d in decs]
        tags = (_JOB.get("tags") or []) if _JOB else []
        want = {(str(t.get("CHAPTER_ID")), str(t.get("BEAT_INDEX"))): str(t.get("LOCATION_ID")) for t in tags}
        binds = [p for d, p in zip(decs, prov) if d["FINAL_STRUCTURED_LOCATION_BIND"] == "YES"]
        rec = {
            "JOB_ID": uuid.uuid4().hex, "TS": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "NOVEL_ID": sc["NOVEL_ID"],
            "R21_ENABLED": enabled(), "BEATS": len(sc["BEATS"]), "DECISIONS": len(decs),
            "CHAPTER_ID": sc.get("CHAPTER_ID") or ",".join(sorted({str(p.get("CHAPTER_ID")) for p in prov if p.get("TAG_FOUND") and p.get("CHAPTER_ID")})),
            "JOB_TAG_STORE_LOAD_COUNT": STATS["TAG_STORE_LOADS"] - sc.get("STATS0", {}).get("TAG_STORE_LOADS", 0),
            "JOB_GOVERNED_LOCATION_STORE_LOAD_COUNT": STATS["LOCATIONS_LOADS"] - sc.get("STATS0", {}).get("LOCATIONS_LOADS", 0),
            "PROCESS_TAG_STORE_LOAD_COUNT": STATS["TAG_STORE_LOADS"], "PROCESS_GOVERNED_LOCATION_STORE_LOAD_COUNT": STATS["LOCATIONS_LOADS"],
            "TAG_STORE_ROWS": len(tags), "TAG_STORE_SHA256": (_JOB or {}).get("store_sha", ""),
            "R21_LOCATION_STEP_P50_MS": q(0.5), "R21_LOCATION_STEP_P95_MS": q(0.95),
            "STRUCTURED_BIND_COUNT": len(binds),
            "UNTAGGED_NEUTRAL_COUNT": sum(1 for d, p in zip(decs, prov) if d["FINAL_STRUCTURED_LOCATION_BIND"] != "YES" and not p.get("TAG_FOUND")),
            "STRUCTURED_BIND_FAILURE_COUNT": sum(1 for d, p in zip(decs, prov) if d["FINAL_STRUCTURED_LOCATION_BIND"] != "YES" and p.get("TAG_FOUND")),
            "UNEXPECTED_LOCATION_CHANGE_COUNT": sum(1 for p in binds if want.get((str(p.get("CHAPTER_ID")), str(p.get("BEAT_INDEX")))) != str(p.get("FINAL_LOCATION_ID"))),
            "STALE_TAG_COUNT": sum(1 for p in prov if p.get("FINAL_LOCATION_REASON") == "HASH_MISMATCH"),
            "UNKNOWN_LOCATION_ID_COUNT": sum(1 for p in prov if p.get("FINAL_LOCATION_REASON") == "UNRESOLVED_ID"),
            "CROSS_NOVEL_REJECTION_COUNT": sum(1 for p in prov if p.get("FINAL_LOCATION_REASON") == "NOVEL_MISMATCH"),
            "ADAPTER_ERROR_COUNT": sum(1 for d in decs if str(d.get("REASON", "")).startswith("ADAPTER_ERROR")),
            "UNTAGGED_POSITIVE_BIND_COUNT": sum(1 for d, p in zip(decs, prov) if d["FINAL_STRUCTURED_LOCATION_BIND"] == "YES" and not p.get("TAG_FOUND")),
            "UNEXPECTED_FALLBACK_COUNT": sum(1 for d in decs if d.get("STRUCTURED_MODE_PROSE_POSITIVE_FALLBACK") == "YES"
                                             or str(d.get("REASON", "")).startswith("ADAPTER_ERROR")),
        }
        LAST_JOB_RECORD.clear(); LAST_JOB_RECORD.update(rec)
        path = os.environ.get(MONITOR_LOG_ENV, "") or _DEFAULT_MONITOR_LOG
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001 - monitoring must never break image production
        pass


def resolve_still(still_index: int, *, lane: str = "") -> Dict[str, Any]:
    """Structured decision for one still (flag ON). Never raises; failures are fail-neutral."""
    out: Dict[str, Any] = {"FINAL_STRUCTURED_LOCATION_BIND": "NO", "LOCATION_RECORD": None, "REASON": "", "PROVENANCE": None,
                           "STRUCTURED_MODE_PROSE_POSITIVE_FALLBACK": "NO", "LANE": lane, "STILL_INDEX": still_index}
    try:
        sc = _SCOPE.get()
        if sc is None or lane == "VISUAL_DIRECTOR":
            out["REASON"] = "BEAT_IDENTITY_UNAVAILABLE"
            _DECISIONS.append(out); return out
        if still_index in sc["DECIDED"]:  # one decision per still per package: every consumer reuses it
            return sc["DECIDED"][still_index]
        if still_index >= len(sc["BEATS"]):
            out["REASON"] = "BEAT_INDEX_OUT_OF_RANGE"; _DECISIONS.append(out); return out
        job = _job(); core = job["core"]
        sha = sc["SHAS"][still_index]
        cid = sc["CHAPTER_ID"]
        if not cid:  # caller lacks a chapter id: take it from the tag whose exact runtime beat hash matches
            hits = {str(t.get("CHAPTER_ID")) for t in job["tags"] if str(t.get("NOVEL_ID", "")).upper() == sc["NOVEL_ID"]
                    and str(t.get("BEAT_INDEX")) == str(still_index) and str(t.get("BEAT_TEXT_SHA256")) == sha}
            cid = hits.pop() if len(hits) == 1 else ""
        STATS["RESOLVES"] += 1
        _t0 = time.perf_counter()
        d = core.decide({"novel_id": sc["NOVEL_ID"], "chapter_id": cid, "beat_index": still_index,
                         "beat_text": sc["BEATS"][still_index]}, tags=job["tags"], governed=job["governed"], run_parser=False,
                        locations_yaml="")  # governed already loaded once per job; no per-beat file read
        sc["STEP_MS"].append((time.perf_counter() - _t0) * 1000)
        d["LOCATIONS_YAML_SHA256"] = job["yaml_sha"]
        d["TAG_STORE_SHA256"] = job["store_sha"]
        d["CHAPTER_ID_SOURCE"] = "CALLER" if sc["CHAPTER_ID"] else ("TAG_EXACT_BEAT_HASH" if cid else "UNAVAILABLE")
        d["BEAT_HASH_SOURCE"] = "RUNTIME_BEAT_TEXT"
        out["PROVENANCE"] = {k: v for k, v in d.items() if k != "SCENE_ENVIRONMENT_SPEC"}
        out["REASON"] = d["FINAL_LOCATION_REASON"]
        if d["FINAL_LOCATION_BIND"] == "YES" and d.get("R12_BIND_ALLOWED"):
            out["FINAL_STRUCTURED_LOCATION_BIND"] = "YES"
            out["LOCATION_RECORD"] = dict(job["governed"][d["FINAL_LOCATION_ID"]]["record"])
            STATS["BINDS"] += 1
        sc["DECIDED"][still_index] = out
    except Exception as exc:  # noqa: BLE001 - fail neutral, never break image production
        out["REASON"] = f"ADAPTER_ERROR:{type(exc).__name__}"
    _DECISIONS.append(out)
    return out


def scene_env_kwargs(still_index: int, legacy_locations: Any, *, lane: str = "") -> Dict[str, Any]:
    """kwargs for tools.scene_environment.resolve_scene_environment at a live call site.
    Flag OFF -> exactly the legacy kwargs. Flag ON -> structured location or none; legacy matcher never consulted."""
    if not enabled():
        return {"locations": legacy_locations}
    if _SCOPE.get() is None or lane in NON_BEAT_ADDRESSABLE_LANES:
        # R21 does not apply: no governed beat identity (Visual Director lane, AIVSB outside a chapter-stills job).
        # Keep the exact legacy location behavior; never synthesize identity, never neutralize.
        _DECISIONS.append({"LANE": lane, "STILL_INDEX": still_index, "R21_ELIGIBLE": "NO",
                           "FINAL_STRUCTURED_LOCATION_BIND": "NOT_APPLICABLE", "REASON": "NOT_BEAT_ADDRESSABLE",
                           "LEGACY_BEHAVIOR_PRESERVED": "YES", "LOCATION_RECORD": None, "PROVENANCE": None})
        return {"locations": legacy_locations}
    d = resolve_still(int(still_index or 0), lane=lane)
    return {"locations": None, "location": d["LOCATION_RECORD"]}


def recent_decisions(clear: bool = False) -> List[Dict[str, Any]]:
    out = list(_DECISIONS)
    if clear:
        _DECISIONS.clear()
    return out
