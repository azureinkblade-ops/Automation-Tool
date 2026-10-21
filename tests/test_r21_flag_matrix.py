"""R21 DEFAULT/PRODUCTION flag matrix (test infrastructure; CPU only, outputs sandboxed by the
live-side-effect barrier). Drives the REAL live path app.make_chapter_image_prompts (wrapped by
_r21_structured_beat_scope) against the committed reference tag store. The leg is chosen by the
ENABLE_STRUCTURED_SCENE_LOCATION value the session was started with (set explicitly per leg).
Prints counts and SHAs only, never beat or chapter prose."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PUSHABLE_STORE = REPO / "data" / "r21_reference" / "writer_tag_store.json"
# LOCAL_FULL_R21_AUTHORITY: untracked, gitignored local copy of the full 20-record qualified store (never pushed).
LOCAL_STORE = REPO / "data" / "r21_reference_local" / "writer_tag_store.json"
STORE_EXPECTED_TAGS = {"C763760A": 20, "DC329320": 19}   # LOCAL_FULL (20) / PUSHABLE (19)
STORE = LOCAL_STORE if LOCAL_STORE.exists() else PUSHABLE_STORE
NEUTRAL_CONTROLS = (("SF-124", 1), ("EN-127", 0), ("EN-127", 2))
MONITOR_LIVE = REPO / "logs" / "r21_job_monitoring.jsonl"
FLAG = "ENABLE_STRUCTURED_SCENE_LOCATION"


def _sha8(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:8].upper()


def _chapter_sources() -> dict:
    """CHAPTER_ID -> chapter metadata from <repo>/chapters/*/metadata.json (untracked local data)."""
    out = {}
    for md in sorted((REPO / "chapters").glob("*/metadata.json")):
        try:
            m = json.loads(md.read_text(encoding="utf-8"))
        except Exception:
            continue
        abbr, n = str(m.get("abbr") or "").upper(), m.get("chapter_number")
        if abbr and n is not None and m.get("chapter_text"):
            out[f"{abbr}-{int(n)}"] = m
    return out


def _stat(p: Path):
    return (p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None


def test_r21_flag_matrix(capsys):
    on = os.environ.get(FLAG, "").strip().lower() in ("1", "true", "yes", "on")
    STORE_SHA8 = _sha8(STORE)
    assert STORE_SHA8 in STORE_EXPECTED_TAGS, "reference tag store changed"
    N = STORE_EXPECTED_TAGS[STORE_SHA8]
    tags = json.loads(STORE.read_text(encoding="utf-8"))["tags"]
    assert len(tags) == N
    srcs = _chapter_sources()
    want_chapters = sorted({t["CHAPTER_ID"] for t in tags})
    missing = [c for c in want_chapters if c not in srcs]
    if missing:
        pytest.skip(f"R21_FIXTURE_MISSING: chapter sources not present for {missing}")

    import app
    from tools import scene_environment as se
    monitor_before = _stat(MONITOR_LIVE)
    os.environ["STRUCTURED_SCENE_LOCATION_TAG_STORE"] = str(STORE)  # not an R21_* bench var
    try:
        decided = {}            # (chapter_id, beat_index) -> bind YES/NO
        beat_sha_match = {}
        for cid in want_chapters:
            m = srcs[cid]
            chapter = str(m["chapter_text"]); title = str(m.get("title") or cid); abbr = str(m["abbr"]).upper()
            novel = str(m.get("novel") or app.NOVEL_NAMES.get(abbr, "") or abbr)
            beats = app.visual_sentences(chapter, 3, novel or title)
            for t in tags:
                if t["CHAPTER_ID"] == cid:
                    i = int(t["BEAT_INDEX"])
                    beat_sha_match[(cid, i)] = i < len(beats) and hashlib.sha256(beats[i].encode("utf-8")).hexdigest() == t["BEAT_TEXT_SHA256"]
            phrases = list(app.fallback_phrases(chapter))[:3]
            w = __import__("sys").modules.get("tools.structured_scene_location_r21_wiring")
            if w is not None:
                w.recent_decisions(clear=True)
            se.recent_still_observability(clear=True)
            app.make_chapter_image_prompts(title, chapter, phrases, novel)
            w = __import__("sys").modules.get("tools.structured_scene_location_r21_wiring")
            for d in (w.recent_decisions(clear=True) if w is not None else []):
                if d.get("STILL_INDEX") is None or d.get("FINAL_STRUCTURED_LOCATION_BIND") == "NOT_APPLICABLE":
                    continue
                k = (cid, int(d["STILL_INDEX"]))
                decided[k] = decided.get(k) == "YES" or d.get("FINAL_STRUCTURED_LOCATION_BIND") == "YES"
                decided[k] = "YES" if decided[k] else "NO"
    finally:
        os.environ.pop("STRUCTURED_SCENE_LOCATION_TAG_STORE", None)

    tagged = {(t["CHAPTER_ID"], int(t["BEAT_INDEX"])) for t in tags}
    tagged_bind = sum(1 for k in tagged if decided.get(k) == "YES")
    neutral_seen = sum(1 for k in NEUTRAL_CONTROLS if k in decided)
    neutral_pos = sum(1 for k in NEUTRAL_CONTROLS if decided.get(k) == "YES")
    all_binds = sum(1 for v in decided.values() if v == "YES")
    res = {"LEG": "PRODUCTION" if on else "DEFAULT", "FLAG": os.environ.get(FLAG, ""),
           "TAG_STORE_SHA8": STORE_SHA8, "AUTHORITY": "LOCAL_FULL" if STORE == LOCAL_STORE else "PUSHABLE", "TAGGED_BEAT_SHA_MATCH": sum(beat_sha_match.values()),
           "TAGGED_BIND_COUNT": tagged_bind, "FAILURE_COUNT": len(tagged) - tagged_bind if on else 0,
           "NEUTRAL_CONTROL_COUNT": neutral_seen, "NEUTRAL_POSITIVE_BIND_COUNT": neutral_pos,
           "STRUCTURED_BIND_COUNT": all_binds,
           "MONITOR_LIVE_LOG_UNCHANGED": _stat(MONITOR_LIVE) == monitor_before}
    assert not [k for k in os.environ if k.upper().startswith("R21_")], "R21_* env must stay cleared"
    with capsys.disabled():
        print("\nR21_FLAG_MATRIX " + json.dumps(res, sort_keys=True))
    assert res["MONITOR_LIVE_LOG_UNCHANGED"]
    assert res["TAGGED_BEAT_SHA_MATCH"] == N, "runtime beats no longer match frozen tag SHAs"
    if on:
        assert tagged_bind == N and res["FAILURE_COUNT"] == 0
        assert neutral_seen == 3 and neutral_pos == 0
        assert all_binds == N
    else:
        assert all_binds == 0 and not decided
