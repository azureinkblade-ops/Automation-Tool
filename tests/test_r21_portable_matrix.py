"""R21 portable CI matrix (test infrastructure; CPU only; no chapters/ needed, no prose).

CI_R21_TEST_SCOPE = PRECOMPUTED_QUALIFIED_BEAT_SHA_TO_BIND.
The qualified Writer/runtime beat SHAs (tests/fixtures/r21_portable_beats.json) are injected at the
authority seam right after runtime hashing:
  * tools.structured_location_authority_r21.sha256_text  (decide(): cur_sha = sha256_text(beat_text))
  * the wiring scope's per-still SHAS list (chapter_beat_scope hashes runtime beats on entry)
Runtime beats are synthetic placeholder tokens; everything after the hash (tag lookup, governed
location resolution, R12 bind gate, wiring decision, job record) is the real production code.
The leg follows ENABLE_STRUCTURED_SCENE_LOCATION as set explicitly for the session.

Governed locations: ALWAYS the test-only structural fixture tests/fixtures/r21_portable_locations.yaml
(9 IDs, id+novel only), injected by monkeypatching core.DEFAULT_LOCATIONS_YAML, on every machine
(with or without private Inkblade data) so CI and local runs exercise the identical input. The test
asserts the barrier saw zero Inkblade Author Studio accesses during the run."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "r21_portable_beats.json"
LOCATIONS = REPO / "tests" / "fixtures" / "r21_portable_locations.yaml"
PORTABLE_LOCATION_IDS = {"en_giant_pod_chamber", "en_nexus_pod", "ha_clinic", "ha_emergency_center",
                         "hp_red_forest_broken_tower", "hp_sect", "hp_village", "sf_forge_heart_cavern",
                         "sf_sanctuary"}
STORE = REPO / "data" / "r21_reference" / "writer_tag_store.json"
MONITOR_LIVE = REPO / "logs" / "r21_job_monitoring.jsonl"
FLAG = "ENABLE_STRUCTURED_SCENE_LOCATION"
CI_R21_TEST_SCOPE = "PRECOMPUTED_QUALIFIED_BEAT_SHA_TO_BIND"


def _token(cid: str, i: int) -> str:
    return f"R21_PORTABLE_PLACEHOLDER::{cid}#{i}"


def _stat(p: Path):
    return (p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None


def test_r21_portable_fixture_shape():
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    recs = fx["RECORDS"]
    assert len(recs) == 22
    assert sum(r["EXPECTED_STRUCTURED_BIND"] for r in recs) == 19
    neu = sorted((r["CHAPTER_ID"], r["BEAT_INDEX"]) for r in recs if not r["EXPECTED_STRUCTURED_BIND"])
    assert neu == [("EN-127", 0), ("EN-127", 2), ("SF-124", 1)]
    for r in recs:
        assert set(r) == {"NOVEL_ID", "CHAPTER_ID", "BEAT_INDEX", "BEAT_TEXT_SHA256", "EXPECTED_LOCATION_ID", "EXPECTED_STRUCTURED_BIND"}
        assert len(r["BEAT_TEXT_SHA256"]) == 64 and int(r["BEAT_TEXT_SHA256"], 16) >= 0
        assert (r["EXPECTED_LOCATION_ID"] is None) == (not r["EXPECTED_STRUCTURED_BIND"])
    tags = json.loads(STORE.read_text(encoding="utf-8"))["tags"]
    sk = {(t["CHAPTER_ID"], int(t["BEAT_INDEX"])): t for t in tags}
    for r in recs:
        k = (r["CHAPTER_ID"], r["BEAT_INDEX"])
        if r["EXPECTED_STRUCTURED_BIND"]:
            assert sk[k]["BEAT_TEXT_SHA256"] == r["BEAT_TEXT_SHA256"] and sk[k]["LOCATION_ID"] == r["EXPECTED_LOCATION_ID"]
        else:
            assert k not in sk and all(t["BEAT_TEXT_SHA256"] != r["BEAT_TEXT_SHA256"] for t in tags)


class InkbladeDefaultPathRead(AssertionError):
    pass


def _guard_default_path(monkeypatch, core):
    """R21_PORTABLE_DEFAULT_PATH_GUARD: point the module path at the fixture BEFORE any loader call and
    wrap the loader so that loading the production default (private Inkblade) path fails the test."""
    production_default = core.DEFAULT_LOCATIONS_YAML
    real_load = core.load_governed_locations
    seen = []

    def guarded(path=None, *a, **k):
        p = os.fspath(path) if path is not None else core.DEFAULT_LOCATIONS_YAML
        seen.append(p)
        if os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath(production_default)) \
                or "inkblade author studio" in p.replace("\\", "/").lower():
            raise InkbladeDefaultPathRead("R21 portable test read the default Inkblade locations path")
        return real_load(p, *a, **k)

    monkeypatch.setattr(core, "DEFAULT_LOCATIONS_YAML", str(LOCATIONS))
    monkeypatch.setattr(core, "load_governed_locations", guarded)
    return seen


def _assert_no_inkblade_access(before: int):
    from tests import live_side_effect_barrier as lsb
    new = lsb.INKBLADE_ACCESSES[before:]
    if new:
        raise InkbladeDefaultPathRead(f"Inkblade Author Studio accessed during portable R21 test: {len(new)}")


def test_r21_default_path_guard_fails_on_inkblade_read(monkeypatch, tmp_path):
    """Self-test: the guard really fails a test that reads the default/Inkblade path (fake temp tree only)."""
    from tools import structured_location_authority_r21 as core
    from tests import live_side_effect_barrier as lsb
    seen = _guard_default_path(monkeypatch, core)
    with pytest.raises(InkbladeDefaultPathRead):
        core.load_governed_locations(os.path.join(str(tmp_path), "Inkblade Author Studio", "locations.yaml"))
    fake = tmp_path / "Inkblade Author Studio" / "x.yaml"
    fake.parent.mkdir()
    before = len(lsb.INKBLADE_ACCESSES)
    try:
        fake.write_text("locations: []", encoding="utf-8")       # barrier records any Inkblade-named access
    except FileNotFoundError:
        pass                                                      # simulated-absent mode refuses it
    with pytest.raises(InkbladeDefaultPathRead):
        _assert_no_inkblade_access(before)
    assert core.load_governed_locations() and seen[-1] == str(LOCATIONS)   # default now resolves to fixture


def test_r21_portable_locations_fixture():
    from tools import structured_location_authority_r21 as core
    from tests import live_side_effect_barrier as lsb
    before = len(lsb.INKBLADE_ACCESSES)
    gov = core.load_governed_locations(str(LOCATIONS))           # explicit fixture path
    assert set(gov) == PORTABLE_LOCATION_IDS and len(gov) == 9
    for lid, g in gov.items():
        assert set(g["record"]) == {"id", "novel"}                # structural fields only, no prose
        assert g["novel"] == lid.split("_")[0].upper() and g["name"] == ""
    store_ids = {t["LOCATION_ID"] for t in json.loads(STORE.read_text(encoding="utf-8"))["tags"]}
    assert PORTABLE_LOCATION_IDS <= store_ids
    assert len(lsb.INKBLADE_ACCESSES) == before


def test_r21_portable_matrix(monkeypatch, capsys):
    on = os.environ.get(FLAG, "").strip().lower() in ("1", "true", "yes", "on")
    recs = json.loads(FIXTURE.read_text(encoding="utf-8"))["RECORDS"]
    from tools import structured_scene_location_r21_wiring as w
    from tools import structured_location_authority_r21 as core

    injected = {_token(r["CHAPTER_ID"], r["BEAT_INDEX"]): r["BEAT_TEXT_SHA256"] for r in recs}
    real_sha = core.sha256_text
    monkeypatch.setattr(core, "sha256_text", lambda text: injected.get(str(text)) or real_sha(text))
    monkeypatch.setenv(w.TAG_STORE_ENV, str(STORE))
    seen = _guard_default_path(monkeypatch, core)               # explicit fixture path; default read fails
    from tests import live_side_effect_barrier as lsb
    inkblade_before = len(lsb.INKBLADE_ACCESSES)
    w._JOB.clear(); w.recent_decisions(clear=True)
    monitor_before = _stat(MONITOR_LIVE)

    by_ch: dict = {}
    for r in recs:
        by_ch.setdefault((r["NOVEL_ID"], r["CHAPTER_ID"]), []).append(r)
    decided, legacy_ok = {}, 0
    legacy = [{"id": "legacy_sentinel"}]
    for (nov, cid), rs in sorted(by_ch.items()):
        n = max(r["BEAT_INDEX"] for r in rs) + 1
        beats = [_token(cid, i) for i in range(n)]
        with w.chapter_beat_scope(nov, beats):                     # production: caller passes no chapter id
            sc = w._SCOPE.get()
            if sc is not None:                                    # seam: right after runtime hashing
                sc["SHAS"] = [injected.get(b) or hashlib.sha256(b.encode("utf-8")).hexdigest() for b in beats]
            for r in rs:
                kw = w.scene_env_kwargs(r["BEAT_INDEX"], legacy)
                if not on:
                    legacy_ok += kw == {"locations": legacy}
                    continue
                d = sc["DECIDED"].get(r["BEAT_INDEX"]) if sc else None
                loc = (kw.get("location") or {}).get("id")
                decided[(cid, r["BEAT_INDEX"])] = (d or {}).get("FINAL_STRUCTURED_LOCATION_BIND") == "YES" and loc is not None, loc
    w._JOB.clear()

    tagged = [r for r in recs if r["EXPECTED_STRUCTURED_BIND"]]
    neutral = [r for r in recs if not r["EXPECTED_STRUCTURED_BIND"]]
    tb = sum(1 for r in tagged if decided.get((r["CHAPTER_ID"], r["BEAT_INDEX"]), (False, None)) == (True, r["EXPECTED_LOCATION_ID"]))
    npos = sum(1 for r in neutral if decided.get((r["CHAPTER_ID"], r["BEAT_INDEX"]), (False, None))[0])
    res = {"CI_R21_TEST_SCOPE": CI_R21_TEST_SCOPE, "LEG": "PRODUCTION" if on else "DEFAULT", "FLAG": os.environ.get(FLAG, ""),
           "CI_R21_TAGGED_BIND_COUNT": tb if on else 0, "FAILURE_COUNT": (len(tagged) - tb) if on else 0,
           "CI_R21_NEUTRAL_COUNT": len(neutral), "NEUTRAL_POSITIVE_BIND_COUNT": npos,
           "CI_R21_STRUCTURED_BIND_COUNT": sum(1 for v in decided.values() if v[0]),
           "DEFAULT_LEGACY_KWARGS_PRESERVED": legacy_ok if not on else None,
           "MONITOR_LIVE_LOG_UNCHANGED": _stat(MONITOR_LIVE) == monitor_before,
           "LOCATIONS_SOURCE": "tests/fixtures/r21_portable_locations.yaml",
           "INKBLADE_RUNTIME_ACCESS_COUNT": len(lsb.INKBLADE_ACCESSES) - inkblade_before,
           "LOADER_PATHS": sorted(set(os.path.basename(x) for x in seen))}
    with capsys.disabled():
        print("\nCI_R21_PORTABLE_MATRIX " + json.dumps(res, sort_keys=True))
    assert res["MONITOR_LIVE_LOG_UNCHANGED"]
    assert res["INKBLADE_RUNTIME_ACCESS_COUNT"] == 0
    _assert_no_inkblade_access(inkblade_before)
    if on:
        assert seen and set(seen) == {str(LOCATIONS)}            # loader called only with the fixture path
    assert not [k for k in os.environ if k.upper().startswith("R21_")]
    if on:
        assert tb == 19 and res["FAILURE_COUNT"] == 0 and len(neutral) == 3 and npos == 0
        assert res["CI_R21_STRUCTURED_BIND_COUNT"] == 19
    else:
        assert res["CI_R21_STRUCTURED_BIND_COUNT"] == 0 and legacy_ok == 22
