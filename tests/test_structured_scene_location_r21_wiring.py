# -*- coding: utf-8 -*-
"""R21_CORE_STRUCTURED_LOCATION_CUTOVER: ENABLE_STRUCTURED_SCENE_LOCATION flag + live adapter tests (CPU only)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLAG = "ENABLE_STRUCTURED_SCENE_LOCATION"
PORTABLE_LOCATIONS = ROOT / "tests" / "fixtures" / "r21_portable_locations.yaml"
H = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
B0 = "The clinic lights hummed over the cracked waiting-room chairs."
B1 = "Rain hammered the alley outside while sirens wailed far away."
B2 = "He counted his breaths and waited for the door to open."


def _tag(cid="HA-900", idx=0, text=B0, loc="ha_clinic", nov="HA", **kw):
    t = {"NOVEL_ID": nov, "CHAPTER_ID": cid, "BEAT_INDEX": idx, "BEAT_TEXT_SHA256": H(text), "LOCATION_ID": loc,
         "LOCATION_SOURCE": "SCENE_METADATA", "TAGGED_BY": "WRITER", "SOURCE_RECORD_ID": f"{cid}#{idx}",
         "SOURCE_SHA256": H(text), "NOTE": ""}
    t.update(kw)
    return t


@pytest.fixture(autouse=True)
def _isolated_monitor_log(tmp_path, monkeypatch):
    monkeypatch.setenv("R21_JOB_MONITOR_LOG", str(tmp_path / "r21_job_monitoring.jsonl"))


@pytest.fixture()
def wiring(tmp_path, monkeypatch):
    from tools import structured_scene_location_r21_wiring as w
    from tools import structured_location_authority_r21 as core
    # Portable: governed locations come from the committed test-only 9-ID fixture, never the private
    # Inkblade default path (production default unchanged; patched before any loader call).
    monkeypatch.setattr(core, "DEFAULT_LOCATIONS_YAML", str(PORTABLE_LOCATIONS))

    def setup(tags, flag="1"):
        store = tmp_path / "tags.json"
        store.write_text(json.dumps({"tags": tags}), encoding="utf-8")
        monkeypatch.setenv(FLAG, flag)
        monkeypatch.setenv(w.TAG_STORE_ENV, str(store))
        w._JOB.clear()
        w.recent_decisions(clear=True)
        return w
    yield setup
    w._JOB.clear()


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    from tools import structured_scene_location_r21_wiring as w
    import app
    assert w.enabled() is False and app._r21_structured_location_on() is False


def test_flag_off_returns_exact_legacy_kwargs(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    import app
    sentinel = [{"id": "x"}]
    assert app._r21_scene_env_kwargs(0, sentinel, "AIVSB") == {"locations": sentinel}
    assert app._r21_scene_env_kwargs(2, None) == {"locations": None}


def test_flag_off_wrapper_calls_straight_through(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    import app
    calls = []
    f = app._r21_structured_beat_scope(lambda t, c, p, n="": calls.append((t, c, p, n)) or ["P"])
    assert f("T", "C", ["a"], "N") == ["P"] and calls == [("T", "C", ["a"], "N")]


def test_flag_off_fresh_process_never_imports_r21():
    code = ("import os,sys;os.environ.pop('ENABLE_STRUCTURED_SCENE_LOCATION',None);sys.path.insert(0,r'%s');"
            "from tools import scene_environment as se;import importlib.util as u;"
            "src=open(r'%s',encoding='utf-8').read();"
            "assert 'from tools import structured_scene_location_r21_wiring' in src;"
            "print(sorted(m for m in sys.modules if 'r21' in m))") % (ROOT, ROOT / "app.py")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


def test_on_valid_tag_binds_via_studio_bible(wiring):
    w = wiring([_tag()])
    with w.chapter_beat_scope("HA", [B0, B1, B2]):
        kw = w.scene_env_kwargs(0, [{"id": "legacy"}], lane="AIVSB")
        d = w.recent_decisions()[-1]
    assert kw["locations"] is None and kw["location"]["id"] == "ha_clinic"
    p = d["PROVENANCE"]
    assert d["FINAL_STRUCTURED_LOCATION_BIND"] == "YES" and p["FINAL_LOCATION_ROLE"] == "CURRENT_SITE" and p["R12_BIND_ALLOWED"]
    assert p["BEAT_HASH_SOURCE"] == "RUNTIME_BEAT_TEXT" and p["CHAPTER_ID"] == "HA-900" and p["SUPPRESSION_PARSER_RUN"] == "NO"


def test_on_spec_uses_structured_location_not_prose(wiring):
    from tools import scene_environment as se
    w = wiring([_tag()])
    with w.chapter_beat_scope("HA", [B0, B1, B2]):
        spec = se.resolve_scene_environment("ha", B0, **w.scene_env_kwargs(0, [{"id": "ha_alley", "novel": "ha", "name": "Back alley"}]))
        spec1 = se.resolve_scene_environment("ha", B1, **w.scene_env_kwargs(1, [{"id": "ha_alley", "novel": "ha", "name": "alley"}]))
    assert spec.location_id == "ha_clinic"
    assert spec1.location_id == "UNRESOLVED"  # untagged: legacy matcher never consulted (prose says 'alley')


@pytest.mark.parametrize("bad", [
    _tag(text="stale text"),                         # stale beat hash
    _tag(loc="ha_nowhere"),                          # unknown id
    _tag(loc="sf_sanctuary"),                        # cross-novel id
    _tag(LOCATION_SOURCE="PROSE"),                   # invalid provenance
    _tag(TAGGED_BY="PARSER"),                        # parser-derived metadata
])
def test_on_invalid_tags_never_bind(wiring, bad):
    w = wiring([bad])
    with w.chapter_beat_scope("HA", [B0, B1, B2]):
        kw = w.scene_env_kwargs(0, [{"id": "legacy"}])
    assert kw == {"locations": None, "location": None}


def test_on_conflicting_tags_never_bind(wiring):
    w = wiring([_tag(), _tag(loc="ha_emergency_center")])
    with w.chapter_beat_scope("HA", [B0, B1, B2]):
        assert w.scene_env_kwargs(0, None)["location"] is None


def test_on_untagged_fail_neutral_but_non_addressable_keeps_legacy(wiring):
    w = wiring([_tag()])
    legacy = [{"id": "x"}]
    assert w.scene_env_kwargs(0, legacy) == {"locations": legacy}  # AIVSB outside chapter-stills job: legacy
    with w.chapter_beat_scope("HA", [B0, B1, B2]):
        assert w.scene_env_kwargs(1, legacy) == {"locations": None, "location": None}  # beat-addressable, untagged
        assert w.scene_env_kwargs(0, legacy, lane="VISUAL_DIRECTOR") == {"locations": legacy}  # VD: legacy
    assert all(d.get("STRUCTURED_MODE_PROSE_POSITIVE_FALLBACK", "NO") == "NO" for d in w.recent_decisions())


def test_visual_director_source_is_pristine():
    assert "ENABLE_STRUCTURED_SCENE_LOCATION" not in (ROOT / "visual_director.py").read_text(encoding="utf-8")


def test_on_loads_store_and_yaml_once_per_job_and_one_decision_per_still(wiring):
    w = wiring([_tag()])
    before = dict(w.STATS)
    for _ in range(3):
        with w.chapter_beat_scope("HA", [B0, B1, B2]):
            for i in (0, 1, 2, 0, 1, 2):
                w.scene_env_kwargs(i, None)
    assert w.STATS["TAG_STORE_LOADS"] - before["TAG_STORE_LOADS"] == 1
    assert w.STATS["LOCATIONS_LOADS"] - before["LOCATIONS_LOADS"] == 1
    assert w.STATS["RESOLVES"] - before["RESOLVES"] == 9


def test_on_never_runs_parser_or_spacy(wiring):
    from tools import structured_location_authority_r21 as core
    w = wiring([_tag()])
    calls = core.STATS["PARSER_CALLS"]
    with w.chapter_beat_scope("HA", [B0, B1, B2]):
        for i in range(3):
            w.scene_env_kwargs(i, None)
    assert core.STATS["PARSER_CALLS"] == calls


def test_on_fresh_process_no_spacy():
    code = ("import os,sys,json,hashlib;sys.path.insert(0,r'%s');os.environ['ENABLE_STRUCTURED_SCENE_LOCATION']='1';"
            "from tools import structured_scene_location_r21_wiring as w\n"
            "with w.chapter_beat_scope('HA',['a','b','c']):\n [w.scene_env_kwargs(i,None) for i in range(3)]\n"
            "print('spacy' in sys.modules)") % ROOT
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_adapter_is_only_live_importer_of_core():
    hits = []
    for p in [ROOT / "app.py", ROOT / "visual_director.py", *sorted((ROOT / "tools").glob("*.py"))]:
        s = p.read_text(encoding="utf-8", errors="ignore")
        if "structured_location_authority_r21" in s and p.name not in ("structured_location_authority_r21.py", "structured_scene_location_r21_wiring.py"):
            hits.append(p.name)
    assert hits == []


def test_job_monitoring_record_written_and_bind_unchanged(wiring, tmp_path, monkeypatch):
    log = tmp_path / "mon.jsonl"
    monkeypatch.setenv("R21_JOB_MONITOR_LOG", str(log))
    w = wiring([_tag(), _tag(idx=2, text=B2, loc="ha_nowhere")])
    with w.chapter_beat_scope("HA", [B0, B1, B2]):
        k = [w.scene_env_kwargs(i, None) for i in range(3)]
    assert k[0]["location"]["id"] == "ha_clinic" and k[1]["location"] is None and k[2]["location"] is None
    rec = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["R21_ENABLED"] is True and rec["STRUCTURED_BIND_COUNT"] == 1 and rec["UNTAGGED_NEUTRAL_COUNT"] == 1
    assert rec["UNKNOWN_LOCATION_ID_COUNT"] == 1 and rec["STRUCTURED_BIND_FAILURE_COUNT"] == 1
    assert rec["UNEXPECTED_LOCATION_CHANGE_COUNT"] == 0 and rec["R21_LOCATION_STEP_P95_MS"] is not None
    for f in ("JOB_ID", "CHAPTER_ID", "PROCESS_TAG_STORE_LOAD_COUNT", "PROCESS_GOVERNED_LOCATION_STORE_LOAD_COUNT",
              "JOB_TAG_STORE_LOAD_COUNT", "JOB_GOVERNED_LOCATION_STORE_LOAD_COUNT", "R21_LOCATION_STEP_P50_MS",
              "STALE_TAG_COUNT", "CROSS_NOVEL_REJECTION_COUNT", "UNEXPECTED_FALLBACK_COUNT", "UNTAGGED_POSITIVE_BIND_COUNT"):
        assert f in rec
    assert rec["UNEXPECTED_FALLBACK_COUNT"] == 0 and rec["UNTAGGED_POSITIVE_BIND_COUNT"] == 0
    first_job_loads = rec["JOB_TAG_STORE_LOAD_COUNT"]
    with w.chapter_beat_scope("HA", [B0, B1, B2]):  # warm second job: no reload, same binds
        k2 = [w.scene_env_kwargs(i, None) for i in range(3)]
    rec2 = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert [x["location"] for x in k2] == [x["location"] for x in k]
    assert rec2["JOB_TAG_STORE_LOAD_COUNT"] == 0 and rec2["JOB_GOVERNED_LOCATION_STORE_LOAD_COUNT"] == 0
    assert rec2["PROCESS_TAG_STORE_LOAD_COUNT"] == rec["PROCESS_TAG_STORE_LOAD_COUNT"] and first_job_loads in (0, 1)
