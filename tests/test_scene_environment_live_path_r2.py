"""SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R2 - live-path scene environment tests (CPU only).

Novel-id seam (A), location decontamination / threshold (B, C), place extractor (D), effective-prompt
differentiation inside the CLIP-77 window (E/F), AIVSB / VD live paths (G, H), identity-OFF HP camera
leak removal (I), env isolation (J), character-home-bias negatives (L), observability (M).
All env changes are monkeypatch-scoped; _env_guard asserts os.environ is restored after every test.
"""
from __future__ import annotations

import io
import os
import re
import sys
import contextlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import scene_environment as se  # noqa: E402
from tools.clip_effective_prompt import effective_prompt, effective_prompt_text  # noqa: E402
from tools.novel_id import ACCEPTED_FORMS, normalize_novel_id  # noqa: E402
import visual_director as vd  # noqa: E402

_ENV_VOLATILE = {"PYTEST_CURRENT_TEST"}
FULL = {"ha": "Heavenly Ascension System", "en": "Eternal Nexus", "hp": "Hundredfold Path", "sf": "Soul Forge Era"}
CHAPTERS = {
    "ha": ("Chapter 9: Stairwell", "Kai climbed the apartment stairwell while the lights flickered above him. "
           "Marta waited in the hallway with a bowl of rice and a worried frown. "
           "Kai stepped onto the rooftop and watched the city lights spread to the horizon."),
    "en": ("Chapter 9: Market", "Kael walked through the night market where vendors shouted over sizzling grills. "
           "He crossed the river docks as cargo cranes groaned in the dark. "
           "Kael stopped at the old library and pressed his palm to the cold door."),
    "hp": ("Chapter 9: Records", "Liang copied the village records in the scribe office by lamplight. "
           "The elder walked with Liang along the riverbank toward the mill. "
           "Liang sat in the night market and listened to the merchants argue about grain."),
    "sf": ("Chapter 9: Hall", "Jarek entered the ruined hall where broken pillars leaned against the walls. "
           "He climbed the collapsed stairway toward the shattered windows. "
           "Jarek knelt in the dust of the ruined hall and touched the cracked floor."),
}


@pytest.fixture(autouse=True)
def _env_guard():
    before = {k: v for k, v in os.environ.items() if k not in _ENV_VOLATILE}
    yield
    after = {k: v for k, v in os.environ.items() if k not in _ENV_VOLATILE}
    leaked = {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert not leaked, f"SCENE_TEST_ENV_LEAK: {leaked}"


def _flags(monkeypatch, identity: bool, vd_on: bool = False, aivsb: bool = True):
    monkeypatch.setenv("ENABLE_IDENTITY_PRESERVATION", "1" if identity else "0")
    monkeypatch.setenv("AIVSB_REASONING_ENABLED", "on" if aivsb else "off")
    if vd_on:
        monkeypatch.setenv("VISUAL_DIRECTOR_ENABLED", "1")
    else:
        monkeypatch.delenv("VISUAL_DIRECTOR_ENABLED", raising=False)


def _norm_tokens(text: str) -> frozenset:
    stop = {"the", "a", "an", "of", "and", "in", "on", "at", "to", "with", "still", "establishing", "travel",
            "climax", "1", "2", "3"}
    return frozenset(w for w in re.findall(r"[a-z]+|\d+", text.lower()) if w not in stop)


# ---- A: novel-id seam --------------------------------------------------------------------------
def test_a_novel_id_accepts_only_documented_forms():
    for form, nid in (("HA", "ha"), ("en", "en"), (" Hp ", "hp"), ("HFP", "hp"), ("sf", "sf"),
                      ("Heavenly Ascension System", "ha"), ("eternal  nexus", "en"), ("Hundredfold Path", "hp"),
                      ("The Hundredfold Path", "hp"), ("SOUL FORGE ERA", "sf"),
                      ("Soulforge Era", "sf")):  # documented production form (app_config.NOVEL_NAMES['SF'])
        assert normalize_novel_id(form) == nid, form
    for bad in ("", None, "Soul-forge Era", "Heavenly", "nexus", "azure inkblade", "hfpx", "h p", "Hundredfold"):
        assert normalize_novel_id(bad) is None, bad
    assert len(ACCEPTED_FORMS) == 11


@pytest.mark.parametrize("nid", ["ha", "en", "hp", "sf"])
@pytest.mark.parametrize("identity", [True, False])
def test_a_g_live_chapter_path_full_name_equals_short_code(monkeypatch, nid, identity):
    import app
    _flags(monkeypatch, identity)
    title, text = CHAPTERS[nid]
    phrases = app.fallback_phrases(text, nid.upper())[:3]
    outs = {}
    for form in (nid.upper(), FULL[nid]):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            outs[form] = app.make_chapter_image_prompts(title, text, phrases, form)
        assert "fell back to legacy" not in buf.getvalue(), (form, buf.getvalue()[-800:])
    assert outs[nid.upper()] == outs[FULL[nid]]
    prompts = outs[FULL[nid]]
    assert all(p.startswith(f"{nid}, expressing") for p in prompts), prompts[0][:80]
    effs = [effective_prompt(p)["EFFECTIVE_PROMPT_HASH"] for p in prompts]
    assert len(set(effs)) == 3
    toks = [_norm_tokens(effective_prompt_text(p)) for p in prompts]
    assert len(set(toks)) == 3
    recs = se.recent_still_observability(clear=True)[-3:]
    assert all(r["NORMALIZED_NOVEL_ID"] == nid and not r["LEGACY_FALLBACK_USED"] for r in recs)
    for r in recs:
        missing = [f for f in se.STILL_OBSERVABILITY_FIELDS if f not in r]
        assert not missing, missing


# ---- B/C/L: decontaminated matcher + evidence threshold + character home bias --------------------
NEGATIVE = [
    ("hp", "Liang wandered through the night market as lanterns swayed", ("hp_sect",)),
    ("hp", "Liang copied the village records in the scribe office", ("hp_sect", "hp_ruins")),
    ("en", "Kael walked along the river docks beneath the cranes", ("en_nexus_pod",)),
    ("ha", "Kai sat in the school library reading quietly", ("ha_alley",)),
    ("sf", "Jarek stood alone in the ruined hall", ("sf_forge",)),
    ("ha", "rain", ("ha_alley",)),
]


@pytest.mark.parametrize("novel,scene,forbidden", NEGATIVE)
def test_b_c_l_character_names_never_bind_home_location(novel, scene, forbidden):
    locs = vd.load_locations()
    det = se.match_studio_bible_location_detailed(scene, locs, novel)
    got = (det["matched"] or {}).get("id")
    assert got not in forbidden, (scene, got, det["candidates"])
    spec = se.resolve_scene_environment(novel, scene, locations=locs)
    assert spec.location_id not in forbidden
    blob = (spec.place_phrase + " " + spec.environment_state).lower()
    for bad in ("mountain sect courtyard", "jade hall", "soul-forge chamber", "nexuspod", "back alley"):
        assert bad not in blob, (scene, blob)


@pytest.mark.parametrize("name", ["Liang", "Kael", "Kai", "Jarek"])
def test_b_name_alone_implies_no_location(name):
    locs = vd.load_locations()
    for novel in ("ha", "en", "hp", "sf"):
        det = se.match_studio_bible_location_detailed(name, locs, novel)
        assert det["matched"] is None
        assert name.lower() in det["rejected_character_tokens"]


def test_b_positive_place_evidence_still_binds():
    locs = vd.load_locations()
    assert se.match_studio_bible_location("Liang enters the ruined sect hall", locs, "hp")["id"] == "hp_sect"
    assert se.match_studio_bible_location("Kael on the megacity skybridge", locs, "en")["id"] == "en_nexus_city"
    assert se.match_studio_bible_location("Jarek at the anvil in the forge", locs, "sf")["id"] == "sf_forge"
    assert se.match_studio_bible_location("Kai collapses in the back alley", locs, "ha")["id"] == "ha_alley"


# ---- D: place extractor -----------------------------------------------------------------------
def test_d_known_bad_place_tokens_rejected_and_real_places_kept():
    bad_text = ("Once again he waited for review. Under the black sky since the fall he slept. "
                "At dawn he woke. In time it passed. At once he ran.")
    acc, rej = se.extract_place_phrases(bad_text)
    assert acc == [], acc
    for good, want in (("Liang sat in the night market", "night market"),
                       ("He copied records in the village scribe office", "village scribe office"),
                       ("Jarek entered the ruined hall", "ruined hall"),
                       ("Kai climbed the apartment stairwell", "apartment stairwell")):
        acc, _ = se.extract_place_phrases(good)
        assert want in acc, (good, acc)


# ---- E/F/G: AIVSB effective prefix ------------------------------------------------------------
def test_e_g_aivsb_full_name_composes_with_distinct_effective_prefix(monkeypatch):
    import app
    _flags(monkeypatch, True)
    beat = "Kai stands in his cramped apartment as the panel flickers above the kitchen counter"
    # character-shape call: the composer continuity adds 'location: ha_alley' for Kai; it must be removed
    # when the scene does not evidence the alley (no fixed character home location).
    shaped = app.compose_aivsb_scene_prompt(FULL["ha"], beat, "kai", still_index=0, still_role="establishing",
                                            composition_goal=beat)
    assert shaped and "location: ha_alley" not in shaped["prompt"]
    assert "ha_alley" in shaped["scene_environment"]["continuity_location_removed"]
    # chapter-path shape (no character id, as make_chapter_image_prompts calls it)
    outs = [app.compose_aivsb_scene_prompt(FULL["ha"], beat, "", still_index=i,
                                           still_role=("establishing", "travel", "climax")[i], composition_goal=beat)
            for i in range(3)]
    assert all(o and o.get("prompt") for o in outs)
    prompts = [o["prompt"] for o in outs]
    for p, o in zip(prompts, outs):
        assert "location: ha_alley" not in p
        assert re.search(r"(?<![A-Za-z0-9_])ha, (?:expressing [^,]{1,120}, )?[A-Za-z0-9_]+ shot\b", p)
        assert not re.search(r"\b(Kai|Kael|Liang|Jarek)\b", effective_prompt_text(p), re.I)
        assert o["scene_environment"]["normalized_novel_id"] == "ha"
        assert "bible_version" in o and "applied_rule_ids" in o
        eff = effective_prompt_text(p)
        assert "setting" in eff and "beat" in eff and "lens" in eff
    assert len({effective_prompt(p)["EFFECTIVE_PROMPT_HASH"] for p in prompts}) == 3
    assert len({effective_prompt(p)["FULL_PROMPT_HASH"] for p in prompts}) == 3


def test_e_clip_window_is_77_with_bos_eos():
    e = effective_prompt("word " * 200)
    assert e["EFFECTIVE_PROMPT_TOKEN_COUNT"] == 75 and e["EFFECTIVE_PROMPT_TRUNCATED"]


# ---- H/I: Visual Director ---------------------------------------------------------------------
@pytest.mark.parametrize("nid", ["ha", "en", "hp", "sf"])
def test_h_vd_full_name_resolves_novel(monkeypatch, nid):
    _flags(monkeypatch, True)
    pkg = vd.build_visual_scene_package(FULL[nid], "", CHAPTERS[nid][1].split(". ")[0])
    assert pkg["normalized_novel_id"] == nid
    assert pkg["image_prompts"][0].startswith(vd.NOVEL_GENRE_LABEL[nid])


@pytest.mark.parametrize("nid", ["ha", "en", "sf"])
@pytest.mark.parametrize("identity", [True, False])
def test_i_no_hp_camera_leak_any_identity_flag(monkeypatch, nid, identity):
    _flags(monkeypatch, identity)
    scene = CHAPTERS[nid][1].split(". ")[0]
    pkg = vd.build_visual_scene_package(nid, "", scene)
    blob = " ".join(pkg["image_prompts"] + [s.get("camera", "") for s in pkg["shots"]]).lower()
    for lm in ("ruined sect hall", "jade altar", "liang"):
        assert lm not in blob, (nid, identity, lm)


def test_i_supported_hp_scene_keeps_hp_landmarks_identity_off(monkeypatch):
    _flags(monkeypatch, False)
    pkg = vd.build_visual_scene_package("hp", "", "Liang enters the ruined sect hall seeking the dormant formation")
    assert "ruined sect hall" in " ".join(pkg["image_prompts"]).lower()


def test_i_unsupported_hp_scene_has_no_hp_landmarks_identity_off(monkeypatch):
    _flags(monkeypatch, False)
    pkg = vd.build_visual_scene_package("hp", "", "Liang copied the village records in the scribe office")
    blob = " ".join(pkg["image_prompts"]).lower()
    assert "ruined sect hall" not in blob and "jade altar" not in blob
