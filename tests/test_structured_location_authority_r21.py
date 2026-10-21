import json, os, subprocess, sys
import pytest
from tools import structured_location_authority_r21 as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
class _DeferredGoverned(dict):
    """Governed Studio Bible locations, loaded on FIRST USE (never at import/collection) from an
    explicit path: the private Inkblade locations.yaml. Tests that use it need private Inkblade data
    and are marked requires_inkblade (tests/fixtures/requires_inkblade_nodes.csv)."""
    _loaded = False

    def _load(self):
        if not self._loaded:
            dict.update(self, M.load_governed_locations(M.DEFAULT_LOCATIONS_YAML))
            self._loaded = True
        return self

    def __getitem__(self, k): return dict.__getitem__(self._load(), k)
    def __contains__(self, k): return dict.__contains__(self._load(), k)
    def __iter__(self): return dict.__iter__(self._load())
    def __len__(self): return dict.__len__(self._load())
    def keys(self): return dict.keys(self._load())
    def items(self): return dict.items(self._load())
    def values(self): return dict.values(self._load())
    def get(self, k, d=None): return dict.get(self._load(), k, d)
    def copy(self): return dict(self._load())


PORTABLE_LOCATIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "r21_portable_locations.yaml")
GOV = _DeferredGoverned()  # no Inkblade read at import time
NEW6 = {"hp_village", "hp_red_forest_broken_tower", "ha_clinic", "ha_emergency_center", "en_giant_pod_chamber", "sf_forge_heart_cavern"}
OLD8 = {"en_nexus_pod", "en_nexus_portal", "en_nexus_city", "ha_alley", "sf_forge", "sf_sanctuary", "hp_sect", "hp_ruins"}
TXT = "Kai stood in the back alley while the rain fell."
GSRC = "IDENTITY_PRESERVATION_STRUCTURED_CONTEXT"
_core_decide = M.decide


def D(*a, **k):  # suppression-layer (fixture-only) path
    k.setdefault("run_parser", True)
    return _core_decide(*a, **k)


def beat(text=TXT, novel="HA", idx=0, depicted=("kai",), src=GSRC):
    b = {"novel_id": novel, "chapter_id": f"{novel}-1", "beat_index": idx, "beat_text": text}
    if depicted is not None:
        b.update(depicted_character_ids=list(depicted), depicted_character_source=src)
    return b


def tag(loc="ha_alley", novel="HA", text=TXT, src="SCENE_METADATA", idx=0, ssha=None):
    return {"NOVEL_ID": novel, "CHAPTER_ID": f"{novel}-1", "BEAT_INDEX": idx, "BEAT_TEXT_SHA256": M.sha256_text(text),
            "LOCATION_ID": loc, "LOCATION_SOURCE": src, "TAGGED_BY": "WRITER",
            "SOURCE_SHA256": M.sha256_text(text) if ssha is None else ssha}


class Spy:
    def __init__(self, records=None):
        self.calls, self.records, self.__name__ = 0, records or [], "spy"
    def __call__(self, text, depicted):
        self.calls += 1
        return {"PARSER_AVAILABLE": True, "records": self.records}


def rec(head, role, subj="Kai", **kw):
    r = {"HEAD": head, "CANONICAL_LOCATION": head, "LOCATION_ROLE": role, "SUBJECT_CHARACTER_ID": subj,
         "PARSER_CONFIDENCE_CLASS": "STRUCTURAL_HIGH", "CLAUSE_REALIS": True, "SUBJECT_IS_DEPICTED": True,
         "FINAL_BIND_ALLOWED": role in ("CURRENT_SITE", "SUCCESSFUL_DESTINATION")}
    r.update(kw); return r


# ---- Studio Bible authority
def test_yaml_is_sole_authority():
    assert set(GOV) == OLD8 | NEW6
    assert M.SHADOW_PENDING_LOCATION_AUTHORITY == "NO" and M.STUDIO_BIBLE_LOCATION_AUTHORITY == "YES"
    assert not hasattr(M, "SHADOW_PENDING_LOCATIONS") and not hasattr(M, "with_shadow_pending")


def test_new_entries_flagged_no_aliases():
    for lid in NEW6:
        r = GOV[lid]["record"]
        assert r.get("legacy_prose_match") is False and "aliases" not in r and lid.split("_")[0].upper() == GOV[lid]["novel"]
    for lid in OLD8:
        assert "legacy_prose_match" not in GOV[lid]["record"]


def test_fixture_may_inject_fake_id_locally():
    g = dict(GOV); g["ha_fake_test"] = {"id": "ha_fake_test", "novel": "HA", "name": "Fake", "record": {}}
    assert D(beat(), tags=[tag(loc="ha_fake_test")], governed=g, parser=Spy())["FINAL_LOCATION_BIND"] == "YES"
    assert D(beat(), tags=[tag(loc="ha_fake_test")], governed=GOV, parser=Spy())["FINAL_LOCATION_REASON"] == "UNRESOLVED_ID"


@pytest.mark.parametrize("lid,novel", [(l, l.split("_")[0].upper()) for l in sorted(NEW6)])
def test_flagged_entries_resolve_structurally(lid, novel):
    d = D(beat(novel=novel, depicted=None), tags=[tag(loc=lid, novel=novel)], governed=GOV, parser=Spy())
    assert d["FINAL_LOCATION_BIND"] == "YES" and d["FINAL_LOCATION_ID"] == lid and d["LEGACY_PROSE_MATCH"] is False


# ---- legacy prose matcher flag skip
def test_legacy_matcher_skips_flagged_entries():
    from tools import scene_environment as S
    import visual_director as VD
    locs = VD.load_locations()
    for text, nov in [("Kai stood in the clinic.", "ha"), ("Across the emergency center, people breathed.", "ha")]:
        assert S.match_studio_bible_location_detailed(text, locs, nov)["matched"] is None
    unflagged = [dict(l, legacy_prose_match=True) if l["id"] == "ha_clinic" else l for l in locs]
    m = S.match_studio_bible_location_detailed("Kai stood in the clinic.", unflagged, "ha")["matched"]
    assert m is not None and m["id"] == "ha_clinic"  # the skip, not the text, is what excludes it


def test_existing_entries_unaffected_by_flag_logic():
    from tools import scene_environment as S
    import visual_director as VD
    locs = VD.load_locations(); old = [l for l in locs if l["id"] in OLD8]
    for text, nov in [("Kai stood in the back alley in the rain.", "ha"), ("Liang crossed the mountain sect courtyard.", "hp"),
                      ("Gray stood in the sanctuary.", "sf")]:
        a = S.match_studio_bible_location_detailed(text, locs, nov)["matched"]
        b = S.match_studio_bible_location_detailed(text, old, nov)["matched"]
        assert (a or {}).get("id") == (b or {}).get("id")


def test_adapter_projection_excludes_flagged_only():
    from tools import studio_bible_adapter as A
    proj = A.build_projection("ha", "HA-1", "Kai stood in the clinic.")
    ids = {l.location_id for l in proj.locations}
    assert not ids & NEW6 and OLD8 <= ids


# ---- reason codes / hash contract
@pytest.mark.parametrize("tags,reason", [
    ([], "MISSING_METADATA"),
    ([tag(src="PROMPT_PROSE")], "MISSING_METADATA"),
    ([tag(text="different text")], "HASH_MISMATCH"),
    ([tag(loc="ha_nowhere")], "UNRESOLVED_ID"),
    ([tag(loc="ha_alley|ha_clinic")], "UNRESOLVED_ID"),
    ([tag(loc="sf_forge")], "NOVEL_MISMATCH"),
    ([tag(), tag(loc="ha_clinic", src="CHAPTER_METADATA")], "CONTRADICTORY"),
])
def test_fail_closed_reasons_and_parser_not_run(tags, reason):
    s = Spy([rec("alley", "CURRENT_SITE")]); d = D(beat(), tags=tags, governed=GOV, parser=s)
    assert d["FINAL_LOCATION_BIND"] == "NO" and d["FINAL_LOCATION_REASON"] == reason
    assert s.calls == 0 and d["SUPPRESSION_PARSER_RUN"] == "NO" and not d["PROSE_FALLBACK_USED"]


def test_stale_hash_never_remaps():
    d = D(beat(), tags=[tag(text=TXT + " ")], governed=GOV, parser=Spy())
    assert d["STRUCTURED_LOCATION_TAG_VALID"] == "NO" and d["FINAL_LOCATION_ID"] == "" and d["FINAL_LOCATION_REASON"] == "HASH_MISMATCH"


@pytest.mark.parametrize("ssha,match", [(None, "BEAT_TEXT"), ("c" * 64, "CHAPTER_SOURCE"), ("", "UNVERIFIED"), ("d" * 64, "UNVERIFIED")])
def test_source_sha_is_provenance_only(ssha, match):
    b = beat(); b["chapter_text_sha256"] = "c" * 64
    d = D(b, tags=[tag(ssha=ssha)], governed=GOV, parser=Spy())
    assert d["FINAL_LOCATION_BIND"] == "YES" and d["SOURCE_SHA256_MATCH"] == match and d["CHAPTER_SOURCE_SHA256"] == "c" * 64
    assert d["SOURCE_RECORD_ID"] and d["BEAT_HASH_BINDING"] == "YES"


def test_cross_novel():
    assert D(beat(), tags=[tag(loc="hp_village")], governed=GOV, parser=Spy())["FINAL_LOCATION_REASON"] == "NOVEL_MISMATCH"
    t = tag(); t["NOVEL_ID"] = "EN"
    assert D(beat(), tags=[t], governed=GOV, parser=Spy())["FINAL_LOCATION_REASON"] == "NOVEL_MISMATCH"


def test_note_carried_and_ignored():
    t = tag(); t["NOTE"] = "PRONOUN_SUBJECT"
    a = D(beat(), tags=[t], governed=GOV, parser=Spy())
    assert a["NOTE"] == "PRONOUN_SUBJECT" and a["FINAL_LOCATION_BIND"] == "YES"


# ---- parser: suppression only, governed character context only
def test_no_character_context_not_evaluated_and_parser_not_called():
    for b in (beat(depicted=None), beat(src="SPACY_GUESS"), beat(depicted=("mina",)), beat(depicted=("liang",))):
        s = Spy([rec("alley", "SOURCE")]); d = D(b, tags=[tag()], governed=GOV, parser=s)
        assert s.calls == 0 and d["PARSER_CONSISTENCY"] == M.NOT_EVALUATED and d["FINAL_LOCATION_BIND"] == "YES"


def test_parser_cannot_create_or_replace():
    d = D(beat(), tags=[], governed=GOV, parser=Spy([rec("alley", "CURRENT_SITE")]))
    assert d["FINAL_LOCATION_BIND"] == "NO" and d["PARSER_CREATED_LOCATION"] is False
    d = D(beat(), tags=[tag(loc="ha_clinic")], governed=GOV, parser=Spy([rec("alley", "UNKNOWN")]))
    assert d["FINAL_LOCATION_ID"] == "ha_clinic"


@pytest.mark.parametrize("records,result", [
    ([], "UNKNOWN"), ([rec("alley", "UNKNOWN")], "AMBIGUOUS"),
    ([rec("alley", "SOURCE", PARSER_CONFIDENCE_CLASS="LOW")], "AMBIGUOUS"), ([rec("alley", "CURRENT_SITE")], "CONSISTENT"),
    ([rec("alley", "SOURCE"), rec("alley", "CURRENT_SITE")], "AMBIGUOUS"),
])
def test_non_contradiction_keeps_location(records, result):
    d = D(beat(), tags=[tag()], governed=GOV, parser=Spy(records))
    assert d["PARSER_CONSISTENCY"] == result and d["FINAL_LOCATION_BIND"] == "YES" and d["SUBJECT_GATE_RUN"]


@pytest.mark.parametrize("r", [rec("alley", "SOURCE"), rec("alley", "FAILED_DESTINATION"), rec("alley", "UNKNOWN", NEGATED=True, PREPOSITION="in"),
                               rec("clinic", "CURRENT_SITE")])
def test_contradiction_suppresses(r):
    d = D(beat(), tags=[tag()], governed=GOV, parser=Spy([r]))
    assert d["PARSER_CONSISTENCY"] == "CONTRADICTORY" and d["FINAL_LOCATION_BIND"] == "NO" and d["FINAL_LOCATION_REASON"] == "CONTRADICTORY"


def test_depicted_gate_and_no_cross_subject_leak():
    d = D(beat(), tags=[tag()], governed=GOV, parser=Spy([rec("alley", "SOURCE", subj="Lena")]))
    assert d["FINAL_LOCATION_BIND"] == "YES" and d["PARSER_EVIDENCE"]["CROSS_SUBJECT_IGNORED"]


def test_multi_character_governed():
    b = beat(text="Gray and Jarek stood in the sanctuary.", novel="SF", depicted=("jarek", "Gray"))
    t = tag(loc="sf_sanctuary", novel="SF", text=b["beat_text"])
    d = D(b, tags=[t], governed=GOV, parser=Spy([rec("sanctuary", "SOURCE", subj="Gray")]))
    assert d["DEPICTED_CONTEXT_VALID"] and d["DEPICTED_IDS_OMITTED"] == ["Gray"] and d["FINAL_LOCATION_BIND"] == "YES"
    d = D(b, tags=[t], governed=GOV, parser=Spy([rec("sanctuary", "SOURCE", subj="Jarek")]))
    assert d["PARSER_CONSISTENCY"] == "CONTRADICTORY"
    d = D(b, tags=[t], governed=GOV, parser=Spy([rec("sanctuary", "SOURCE", subj="Voss")]))
    assert d["FINAL_LOCATION_BIND"] == "YES"


PROV = ["NOVEL_ID", "CHAPTER_ID", "BEAT_INDEX", "BEAT_TEXT_SHA256", "LOCATION_ID", "LOCATION_SOURCE", "SOURCE_RECORD_ID",
        "SOURCE_VERSION", "SOURCE_SHA256", "SOURCE_SCOPE", "CHAPTER_SOURCE_SHA256", "TAGGED_BY", "STUDIO_BIBLE_LOCATION_ID",
        "TAG_VALID", "PARSER_CONSISTENCY", "FINAL_LOCATION_BIND", "FINAL_LOCATION_REASON", "SUPPRESSION_PARSER_RUN",
        "PROSE_FALLBACK_USED", "AUTHORITY_ORDER", "LOCATIONS_YAML_SHA256", "DECISION_ID", "MODULE_VERSION",
        "DEPICTED_CHARACTER_IDS", "DEPICTED_CHARACTER_SOURCE", "DEPICTED_CONTEXT_VALID"]


@pytest.mark.parametrize("tags", [[], [tag()], [tag(text="x")]])
def test_provenance_complete(tags):
    d = D(beat(), tags=tags, governed=GOV, parser=Spy())
    assert all(k in d for k in PROV)


def test_real_r20_with_governed_context():
    pytest.importorskip("spacy")
    t1 = "Kai stood in the back alley."
    d = D(beat(t1), tags=[tag(text=t1)], governed=GOV)
    assert d["PARSER_CONSISTENCY"] == "CONSISTENT" and d["FINAL_LOCATION_BIND"] == "YES"
    t2 = "Kai left the back alley and ran."
    d = D(beat(t2), tags=[tag(text=t2)], governed=GOV)
    assert d["PARSER_CONSISTENCY"] == "CONTRADICTORY" and d["FINAL_LOCATION_BIND"] == "NO"
    # R21.3: tagged-location check covers nouns outside the R20 ontology (same parse, no reparse)
    t3 = "Kai left the clinic and ran into the rain."
    d = D(beat(t3), tags=[tag(loc="ha_clinic", text=t3)], governed=GOV)
    assert d["FINAL_LOCATION_BIND"] == "NO" and d["FINAL_LOCATION_ID"] == ""


def test_untagged_and_character_lookup_never_load_spacy_fresh_process(tmp_path):
    store = tmp_path / "empty.json"; store.write_text(json.dumps({"tags": []}))
    code = ("import sys,json; from tools import structured_location_authority_r21 as M\n"
            "v=M.validate_depicted_context('HA',['kai'],'IDENTITY_PRESERVATION_STRUCTURED_CONTEXT')\n"
            f"rs=[M.decide({{'novel_id':'HA','chapter_id':'HA-1','beat_index':i,'beat_text':'Kai stood in the clinic.','depicted_character_ids':['kai'],'depicted_character_source':'IDENTITY_PRESERVATION_STRUCTURED_CONTEXT'}}, {str(store)!r}) for i in range(20)]\n"
            "print(json.dumps({'spacy':'spacy' in sys.modules,'r20':'tools.place_detection_r20' in sys.modules,'calls':M.STATS['PARSER_CALLS'],'binds':sum(r['FINAL_LOCATION_BIND']=='YES' for r in rs),'valid':v['VALID']}))")
    cp = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert cp.returncode == 0, (cp.stderr.strip().splitlines() or [""])[-1][:300]
    out = cp.stdout
    assert json.loads(out.strip().splitlines()[-1]) == {"spacy": False, "r20": False, "calls": 0, "binds": 0, "valid": True}


def test_module_not_imported_by_live_paths():
    for f in ("app.py", "visual_director.py", os.path.join("tools", "scene_environment.py"), os.path.join("tools", "studio_bible_adapter.py")):
        with open(os.path.join(ROOT, f), encoding="utf-8", errors="ignore") as fh:
            assert "structured_location_authority_r21" not in fh.read()



# ---- R21.3 remediation: hash-bound character context + tagged-location contradiction check
SUPPRESS_FX = [("HA", "ha_clinic", ["kai"], "Kai left the clinic."), ("SF", "sf_sanctuary", ["jarek"], "Jarek left the sanctuary."),
               ("HA", "ha_clinic", ["kai"], "Kai had left the clinic."), ("HA", "ha_clinic", ["kai"], "Kai was no longer at the clinic."),
               ("HA", "ha_clinic", ["kai"], "Kai left the clinic and went toward the station."),
               ("HA", "ha_clinic", ["kai"], "Kai left the clinic behind him."), ("HA", "ha_clinic", ["kai"], "Kai never reached the clinic."),
               ("HA", "ha_clinic", ["kai"], "Kai was not in the clinic."), ("HA", "ha_clinic", ["kai"], "Kai walked out of the clinic.")]
KEEP_FX = [("HA", "ha_clinic", ["kai"], "Kai left his bag at the clinic."), ("SF", "sf_sanctuary", ["jarek"], "Jarek left the sanctuary door open."),
           ("SF", "sf_sanctuary", ["jarek"], "The sanctuary was all he had left."),
           ("HA", "ha_clinic", ["kai"], "Kai left the clinic at dawn and returned by noon."), ("HA", "ha_clinic", ["kai"], "Mina left the clinic."),
           ("HA", "ha_clinic", ["kai"], "Kai entered the clinic."), ("HA", "ha_clinic", ["kai"], "Kai arrived at the clinic."),
           ("HA", "ha_clinic", ["kai"], "Kai left the station."), ("HA", "ha_clinic", ["kai"], "Kai never left the clinic."),
           ("HA", "ha_clinic", ["kai"], "Kai might leave the clinic."), ("HA", "ha_clinic", ["kai"], "He left the clinic.")]


def _fx(nov, loc, dep, text):
    b = {"novel_id": nov, "chapter_id": "X", "beat_index": 0, "beat_text": text, "depicted_character_ids": dep, "depicted_character_source": GSRC}
    t = {"NOVEL_ID": nov, "CHAPTER_ID": "X", "BEAT_INDEX": 0, "BEAT_TEXT_SHA256": M.sha256_text(text), "LOCATION_ID": loc, "LOCATION_SOURCE": "SCENE_METADATA"}
    return D(b, tags=[t], governed=GOV)


@pytest.mark.parametrize("fx", SUPPRESS_FX)
def test_tagged_location_contradiction_suppresses(fx):
    pytest.importorskip("spacy")
    d = _fx(*fx)
    assert d["FINAL_LOCATION_BIND"] == "NO" and d["FINAL_LOCATION_REASON"] == "CONTRADICTORY" and d["FINAL_LOCATION_ID"] == ""
    assert d["CLAUSE_REPARSE_COUNT"] in (0, None)


@pytest.mark.parametrize("fx", KEEP_FX)
def test_tagged_location_negatives_keep(fx):
    pytest.importorskip("spacy")
    d = _fx(*fx)
    assert d["FINAL_LOCATION_BIND"] == "YES" and d["FINAL_LOCATION_ID"] == fx[1]


def test_station_never_created():
    pytest.importorskip("spacy")
    d = _fx("HA", "ha_clinic", ["kai"], "Kai left the clinic and went toward the station.")
    assert "station" not in json.dumps({k: d[k] for k in ("FINAL_LOCATION_ID", "STUDIO_BIBLE_LOCATION_ID", "LOCATION_ID")})


def test_canonical_ids_only_invalid_omitted():
    v = M.validate_depicted_context("EN", ["kael", "kael_veyra", "jarek", "he"], GSRC)
    assert v["KEYS"] == ["kael_veyra"] and set(v["OMITTED"]) == {"kael", "jarek", "he"}
    # 'Gray' is in GOVERNED_NOVEL_CAST but has no identity contract and no mapping to jarek -> rejected
    for g in ("Gray", "gray"):
        v = M.validate_depicted_context("SF", [g], GSRC)
        assert not v["VALID"] and v["OMITTED"] == [g]


def test_character_context_hash_bound_and_stale_unusable():
    ctx = [{"NOVEL_ID": "HA", "CHAPTER_ID": "HA-1", "BEAT_INDEX": 0, "BEAT_TEXT_SHA256": M.sha256_text(TXT + "x"),
            "DEPICTED_CHARACTER_IDS": ["kai"], "DEPICTED_CHARACTER_SOURCE": GSRC}]
    s = Spy([rec("alley", "SOURCE")])
    d = D(beat(depicted=None), tags=[tag()], governed=GOV, parser=s, character_contexts=ctx)
    assert d["CHARACTER_CONTEXT_STALE"] and s.calls == 0 and d["PARSER_CONSISTENCY"] == M.NOT_EVALUATED and d["FINAL_LOCATION_BIND"] == "YES"
    ctx[0]["BEAT_TEXT_SHA256"] = M.sha256_text(TXT)
    d = D(beat(depicted=None), tags=[tag()], governed=GOV, parser=s, character_contexts=ctx)
    assert s.calls == 1 and d["PARSER_CONSISTENCY"] == "CONTRADICTORY"


def test_cast_loaded_once_per_job():
    n = M.STATS["CAST_LOADS"]
    for _ in range(50):
        M.validate_depicted_context("HA", ["kai"], GSRC)
    assert M.STATS["CAST_LOADS"] - n <= 1




# ---- R21 CORE (Option 2): suppression deferred
def test_core_default_never_runs_parser():
    s = Spy([rec("alley", "SOURCE")])
    d = _core_decide(beat(), tags=[tag()], governed=GOV, parser=s)
    assert s.calls == 0 and d["SUPPRESSION_PARSER_RUN"] == "NO" and d["FINAL_LOCATION_BIND"] == "YES" and d["R12_BIND_ALLOWED"]
    assert M.PARSER_SUPPRESSION_PRODUCTION_ENABLED == "NO" and M.PARSER_SUPPRESSION_QUALIFIED == "NO"


def test_core_tagged_path_no_spacy_fresh_process(tmp_path):
    t = {"NOVEL_ID": "HA", "CHAPTER_ID": "HA-1", "BEAT_INDEX": 0, "BEAT_TEXT_SHA256": M.sha256_text(TXT), "LOCATION_ID": "ha_clinic",
         "LOCATION_SOURCE": "SCENE_METADATA", "TAGGED_BY": "WRITER"}
    store = tmp_path / "s.json"; store.write_text(json.dumps({"tags": [t]}))
    code = ("import sys,json; from tools import structured_location_authority_r21 as M\n"
            f"r=M.decide({{'novel_id':'HA','chapter_id':'HA-1','beat_index':0,'beat_text':{TXT!r}}}, {str(store)!r}, locations_yaml={str(PORTABLE_LOCATIONS)!r})\n"
            "print(json.dumps({'spacy':'spacy' in sys.modules,'r20':'tools.place_detection_r20' in sys.modules,'bind':r['FINAL_LOCATION_BIND']}))")
    cp = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert cp.returncode == 0, (cp.stderr.strip().splitlines() or [""])[-1][:300]
    out = cp.stdout
    assert json.loads(out.strip().splitlines()[-1]) == {"spacy": False, "r20": False, "bind": "YES"}


@pytest.mark.parametrize("tb", ["PARSER", "spacy", "R20", "MODEL"])
def test_parser_derived_tag_rejected(tb):
    t = tag(); t["TAGGED_BY"] = tb
    d = _core_decide(beat(), tags=[t], governed=GOV)
    assert d["FINAL_LOCATION_BIND"] == "NO" and d["FINAL_LOCATION_REASON"] == "MISSING_METADATA"


def test_r12_roles_match_r6():
    import re as _re
    src = open(os.path.join(ROOT, "tools", "location_relation_r6.py"), encoding="utf-8").read()
    m = _re.search(r"_BIND_ROLES = frozenset\(\{([^}]*)\}\)", src)
    assert set(_re.findall(r'"([A-Z_]+)"', m.group(1))) == set(M.R12_BIND_ROLES)
