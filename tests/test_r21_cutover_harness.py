# -*- coding: utf-8 -*-
"""R21 cutover review harness (CPU, no images). Runs only when R21_HARNESS_OUT is set; otherwise skipped.
Drives the live composition path make_chapter_image_prompts over the exported chapters and records prompts +
scene-environment observability per still, for flag OFF/ON comparison."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

OUT = os.environ.get("R21_HARNESS_OUT", "")
# Test/harness default: the committed R21 reference copy (production keeps reading .env.local).
REFERENCE_TAG_STORE = str(Path(__file__).resolve().parent.parent / "data" / "r21_reference" / "writer_tag_store.json")

os.environ.setdefault("R21_JOB_MONITOR_LOG", os.path.join(os.environ.get("TEMP", "/tmp"), "r21_harness_monitor.jsonl"))
_VOLATILE = {"timestamp", "time", "ts", "created_at", "run_id", "TIMESTAMP"}


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in sorted(o.items()) if k not in _VOLATILE}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o if isinstance(o, (str, int, float, bool)) or o is None else str(o)


def _chapters(root: Path):
    best = {}
    for md in sorted((root / "chapters").glob("*/metadata.json")):
        try:
            m = json.loads(md.read_text(encoding="utf-8"))
        except Exception:
            continue
        abbr, n = str(m.get("abbr") or "").upper(), m.get("chapter_number")
        if abbr and n is not None and m.get("chapter_text"):
            best[f"{abbr}-{int(n)}"] = m
    keep = set(json.loads(os.environ["R21_HARNESS_CHAPTERS"])) if os.environ.get("R21_HARNESS_CHAPTERS") else None
    return {k: v for k, v in sorted(best.items()) if keep is None or k in keep}


@pytest.mark.skipif(not OUT, reason="R21 cutover harness runs only on request")
def test_r21_cutover_harness():
    import app
    from tools import scene_environment as se
    root = Path(app.__file__).resolve().parent
    lane = os.environ.get("R21_HARNESS_LANE", "DEFAULT")
    res = {"LANE": lane, "FLAG": os.environ.get("ENABLE_STRUCTURED_SCENE_LOCATION", ""), "chapters": {}}
    se.recent_still_observability(clear=True)
    for cid, m in _chapters(root).items():
        chapter = str(m["chapter_text"]); title = str(m.get("title") or cid); abbr = str(m["abbr"]).upper()
        phrases = list(app.fallback_phrases(chapter))[:3]
        t0 = time.perf_counter()
        err = ""
        try:
            novel_arg = str(m.get("novel") or app.NOVEL_NAMES.get(abbr, "") or abbr)  # what make_campaign passes
            prompts = app.make_chapter_image_prompts(title, chapter, phrases, novel_arg)
        except Exception as exc:  # noqa: BLE001
            prompts, err = [], f"{type(exc).__name__}: {exc}"
        ms = (time.perf_counter() - t0) * 1000
        obs = _clean(se.recent_still_observability(clear=True))
        stills = []
        for i in range(max(len(prompts), len(obs))):
            rec = {"PROMPT": prompts[i] if i < len(prompts) else None, "OBS": obs[i] if i < len(obs) else None}
            rec["SHA"] = hashlib.sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            stills.append(rec)
        dec = []
        if "tools.structured_scene_location_r21_wiring" in sys.modules:
            dec = _clean(sys.modules["tools.structured_scene_location_r21_wiring"].recent_decisions(clear=True))
        res["chapters"][cid] = {"MS": ms, "ERROR": err, "N_PROMPTS": len(prompts), "stills": stills, "R21": dec}
    res["R21_MODULES_LOADED"] = sorted(m for m in sys.modules if "r21" in m)
    w = sys.modules.get("tools.structured_scene_location_r21_wiring")
    c = sys.modules.get("tools.structured_location_authority_r21")
    res["WIRING_STATS"] = dict(w.STATS) if w else None
    res["CORE_STATS"] = dict(c.STATS) if c else None
    Path(OUT).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")


_BENCH = os.environ.get("R21_BENCH_OUT", "")
_TRACE = os.environ.get("R21_TRACE_OUT", "")


@pytest.mark.skipif(not _TRACE, reason="fresh-process trace runs only on request")
def test_r21_fresh_process_trace():
    """Fresh process: record module imports + file opens across a live make_chapter_image_prompts job."""
    opened = []
    sys.addaudithook(lambda ev, args: opened.append(str(args[0])) if ev == "open" and args and isinstance(args[0], (str, bytes)) else None)
    import app
    root = Path(app.__file__).resolve().parent
    chs = list(_chapters(root).items())[:12]
    for cid, m in chs:
        app.make_chapter_image_prompts(str(m.get("title") or cid), str(m["chapter_text"]), list(app.fallback_phrases(str(m["chapter_text"])))[:3],
                                       str(m.get("novel") or app.NOVEL_NAMES.get(str(m["abbr"]).upper(), "")))
    store = os.environ.get("STRUCTURED_SCENE_LOCATION_TAG_STORE", "") or REFERENCE_TAG_STORE
    res = {"FLAG": os.environ.get("ENABLE_STRUCTURED_SCENE_LOCATION", ""), "CHAPTERS": len(chs),
           "R21_MODULES": sorted(m for m in sys.modules if "r21" in m and not m.startswith("tests")),
           "SPACY_IN_SYS_MODULES": "spacy" in sys.modules,
           "TAG_STORE_OPENS": sum(1 for o in opened if Path(store).name in o),
           "LOCATIONS_YAML_OPENS": sum(1 for o in opened if o.replace("\\", "/").endswith("locations/locations.yaml")),
           "R21_SOURCE_OPENS": sorted({o for o in opened if "r21" in o.lower() and o.endswith((".py", ".pyc"))})}
    w = sys.modules.get("tools.structured_scene_location_r21_wiring")
    res["WIRING_STATS"] = dict(w.STATS) if w else None
    Path(_TRACE).write_text(json.dumps(res, indent=1), encoding="utf-8")


@pytest.mark.skipif(not _BENCH, reason="bench runs only on request")
def test_r21_adapter_bench():
    """Per-still structured decision cost inside the live adapter (flag ON), first beat separate."""
    import statistics
    from tools import structured_scene_location_r21_wiring as w
    beats = [json.loads(l) for l in open(os.environ["R21_BEATS_JSONL"], encoding="utf-8")]
    tags = json.load(open(os.environ.get("STRUCTURED_SCENE_LOCATION_TAG_STORE", "") or REFERENCE_TAG_STORE, encoding="utf-8"))
    tags = tags.get("tags", tags) if isinstance(tags, dict) else tags
    tagged = {(t["CHAPTER_ID"], int(t["BEAT_INDEX"])) for t in tags}
    by_ch = {}
    for b in beats:
        by_ch.setdefault(b["CHAPTER_ID"], []).append(b)
    names = {"HA": "Hollow Ascension", "EN": "Eternal Nexus", "HP": "Heaven's Path", "SF": "Soulforge Era"}
    first = None; t_tag, t_un = [], []
    for rep in range(5):
        for cid, bs in by_ch.items():
            with w.chapter_beat_scope(bs[0]["NOVEL_ID"], [b["BEAT_TEXT"] for b in bs]):
                for b in bs:
                    t0 = time.perf_counter(); d = w.scene_env_kwargs(int(b["BEAT_INDEX"]), None, lane="AIVSB"); ms = (time.perf_counter() - t0) * 1000
                    if first is None:
                        first = ms; continue
                    (t_tag if (cid, int(b["BEAT_INDEX"])) in tagged else t_un).append(ms)
    q = lambda v: {"p50": round(statistics.median(v), 4), "p95": round(sorted(v)[int(0.95 * len(v)) - 1], 4), "n": len(v)}
    Path(_BENCH).write_text(json.dumps({"FIRST_BEAT_MS_INCL_JOB_LOAD": round(first, 3), "TAGGED": q(t_tag), "UNTAGGED": q(t_un),
                                        "STATS": dict(w.STATS), "SPACY_IN_SYS_MODULES": "spacy" in sys.modules}, indent=1), encoding="utf-8")


_IBENCH = os.environ.get("R21_INTERLEAVED_OUT", "")


@pytest.mark.skipif(not _IBENCH, reason="interleaved bench runs only on request")
def test_r21_interleaved_full_path_bench():
    """Warm, interleaved full live-path timing: per chapter, run arms in alternating order within one process."""
    import statistics
    import app
    root = Path(app.__file__).resolve().parent
    chs = list(_chapters(root).items())
    arms = os.environ.get("R21_ARMS", "OFF,ON").split(",")
    store = os.environ.get("R21_STORE", "") or REFERENCE_TAG_STORE

    def call(arm, m, cid):
        if arm.startswith("ON"):
            os.environ["ENABLE_STRUCTURED_SCENE_LOCATION"] = "1"; os.environ["STRUCTURED_SCENE_LOCATION_TAG_STORE"] = store
        else:
            os.environ.pop("ENABLE_STRUCTURED_SCENE_LOCATION", None)
        ch = str(m["chapter_text"])
        t0 = time.perf_counter()
        app.make_chapter_image_prompts(str(m.get("title") or cid), ch, list(app.fallback_phrases(ch))[:3],
                                       str(m.get("novel") or app.NOVEL_NAMES.get(str(m["abbr"]).upper(), "")))
        return (time.perf_counter() - t0) * 1000

    for cid, m in chs[:10]:  # warm-up both arms
        for a in arms:
            call(a, m, cid)
    t = {a: [] for a in arms}
    for rep in range(int(os.environ.get("R21_REPS", "3"))):
        for j, (cid, m) in enumerate(chs):
            order = arms if (j + rep) % 2 == 0 else list(reversed(arms))
            for a in order:
                t[a].append(call(a, m, cid))
    os.environ.pop("ENABLE_STRUCTURED_SCENE_LOCATION", None)
    q = lambda v: {"p50": round(statistics.median(v), 2), "p95": round(sorted(v)[int(0.95 * len(v)) - 1], 2), "n": len(v)}
    w = sys.modules.get("tools.structured_scene_location_r21_wiring")
    Path(_IBENCH).write_text(json.dumps({"UNIT": "ms per 3-still chapter package (full live make_chapter_image_prompts)",
                                         "ARMS": {a: q(v) for a, v in t.items()},
                                         "WIRING_STATS": dict(w.STATS) if w else None,
                                         "SPACY_IN_SYS_MODULES": "spacy" in sys.modules}, indent=1), encoding="utf-8")
