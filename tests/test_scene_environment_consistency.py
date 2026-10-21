"""SCENE_ENVIRONMENT_CONSISTENCY_REMEDIATION — 22-case test matrix (Parts I–M).

CPU-only. No image generation. Does not weaken identity/wardrobe/held-prop/effects.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R2 (Part J): no process-wide env mutation at import or in
# tests. ENABLE_IDENTITY_PRESERVATION / AIVSB_REASONING_ENABLED are set per test via monkeypatch
# and restored automatically; _env_guard proves os.environ after each test equals the pre-test state.

from tools.scene_environment import (  # noqa: E402
    AUTHORITY_PRECEDENCE,
    HP_HARD_LANDMARKS,
    UNRESOLVED,
    UNSPECIFIED,
    assert_domain_separation,
    match_studio_bible_location,
    reject_cross_novel_landmarks,
    resolve_scene_environment,
    still_differentiation_fragment,
)
import visual_director as vd  # noqa: E402


SCENES = {
    "ha": [
        "Kai stands in his cramped apartment as the system panel flickers to life above the kitchen counter",
        "Kai climbs the apartment stairwell counting steps while azure meridian light threads along the railing",
        "Kai faces Marta in the hallway after completing the emergency endurance task",
    ],
    "en": [
        "Kael Veyra raises his soulblade under neon rain on the megacity skybridge",
        "Kael moves through the Shadowforge initiation chamber lit by holographic sigils",
        "Kael watches traffic streams from a rooftop overlooking the neon city grid",
    ],
    "hp": [
        "Liang enters the ruined sect hall seeking the dormant formation",
        "Liang climbs the broken stair toward the jade altar",
        "Liang kneels before the altar as silver qi threads awaken",
    ],
    "sf": [
        "Jarek drags iron chains through the ash-choked forge halls of Soulforge Era",
        "Jarek stands before the bellows as cinders swirl in the industrial forge",
        "Jarek crosses the slag courtyard under a soot-stained sky",
    ],
}


_ENV_VOLATILE = {"PYTEST_CURRENT_TEST"}


@pytest.fixture(autouse=True)
def _env_guard():
    """Set up before (and torn down after) monkeypatch: os.environ must be restored exactly."""
    before = {k: v for k, v in os.environ.items() if k not in _ENV_VOLATILE}
    yield
    after = {k: v for k, v in os.environ.items() if k not in _ENV_VOLATILE}
    leaked = {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert not leaked, f"SCENE_TEST_ENV_LEAK: {leaked}"


@pytest.fixture(autouse=True)
def _scoped_identity_on(_env_guard, monkeypatch):
    # Original intent of the module (identity ON scene matrix), now test-scoped.
    monkeypatch.setenv("ENABLE_IDENTITY_PRESERVATION", "1")
    yield


def _blob_pkg(pkg: dict) -> str:
    shots = pkg.get("shots") or []
    return "\n".join(
        list(pkg.get("image_prompts") or [])
        + [s.get("camera", "") for s in shots]
        + [str(s.get("environment_state", "")) for s in shots]
        + [str(s.get("action", "")) for s in shots]
    )


# ---- 22 cases -----------------------------------------------------------------

def test_01_authority_precedence_order():
    assert AUTHORITY_PRECEDENCE == (
        "TEXT_CANON_SCENE",
        "STUDIO_BIBLE_LOCATION",
        "SCENE_CONTEXT",
        "VISUAL_DIRECTION",
        "MODEL_PRIOR",
    )


def test_02_scene_environment_spec_fields():
    locs = vd.load_locations()
    spec = resolve_scene_environment("en", SCENES["en"][0], locations=locs)
    d = spec.to_dict()
    for k in ("location_id", "authority", "place_phrase", "still_role", "observability"):
        assert k in d


def test_03_en_matches_studio_bible_city():
    locs = vd.load_locations()
    loc = match_studio_bible_location(SCENES["en"][0], locs, "en")
    assert loc is not None
    assert loc.get("id") == "en_nexus_city"


def test_04_sf_matches_forge():
    locs = vd.load_locations()
    loc = match_studio_bible_location(SCENES["sf"][0], locs, "sf")
    assert loc is not None
    assert loc.get("id") == "sf_forge"


def test_05_ha_apartment_unspecified_no_borrow():
    locs = vd.load_locations()
    loc = match_studio_bible_location(SCENES["ha"][0], locs, "ha")
    assert loc is None  # no HA apartment in Studio Bible
    spec = resolve_scene_environment("ha", SCENES["ha"][0], locations=locs)
    assert spec.location_id in (UNSPECIFIED, UNRESOLVED)  # R2: no-evidence sentinel is UNRESOLVED
    assert spec.unknown_location is True
    # Must not borrow EN apartment
    assert "Kael's" not in spec.place_phrase
    assert "nexuspod" not in spec.place_phrase.lower()


def test_06_hp_landmarks_only_on_hp():
    for novel in ("ha", "en", "sf"):
        pkg = vd.build_visual_scene_package(novel, "1", SCENES[novel][0])
        blob = _blob_pkg(pkg).lower()
        for lm in ("ruined sect hall", "jade altar"):
            assert lm not in blob, f"{novel} leaked {lm}"


def test_07_hp_keeps_landmarks_when_supported():
    pkg = vd.build_visual_scene_package("hp", "1", SCENES["hp"][0])
    blob = _blob_pkg(pkg).lower()
    assert "ruined sect hall" in blob or "jade altar" in blob


def test_08_unknown_location_neutral_no_foreign():
    pkg = vd.build_visual_scene_package("ha", "1", SCENES["ha"][0])
    blob = _blob_pkg(pkg).lower()
    for lm in HP_HARD_LANDMARKS:
        assert lm not in blob
    se = pkg.get("scene_environment") or {}
    assert se.get("unknown_location") is True or se.get("location_id") == UNSPECIFIED


def test_09_cross_novel_landmark_rejection_helper():
    assert reject_cross_novel_landmarks("ha", "Kai in the ruined sect hall")
    assert not reject_cross_novel_landmarks("hp", "Liang in the ruined sect hall")


def test_10_scene_specific_composition_across_scenes():
    for novel, scenes in SCENES.items():
        bundles = []
        for i, s in enumerate(scenes):
            pkg = vd.build_visual_scene_package(novel, str(i + 1), s)
            cams = "||".join(sh.get("camera", "") for sh in (pkg.get("shots") or []))
            bundles.append(cams)
        assert len(set(bundles)) == len(scenes), f"{novel} cameras not scene-specific"


def test_11_multi_still_differentiation_within_package():
    pkg = vd.build_visual_scene_package("en", "1", SCENES["en"][0])
    prompts = pkg.get("image_prompts") or []
    assert len(prompts) == 3
    assert len(set(prompts)) == 3


def test_12_vd_receives_location_action_still_role():
    pkg = vd.build_visual_scene_package("sf", "1", SCENES["sf"][0])
    shots = pkg.get("shots") or []
    assert shots
    for i, sh in enumerate(shots):
        assert "still_index" in sh
        assert "still_role" in sh
        assert "composition_goal" in sh
        assert "location_id" in sh
        assert sh["still_index"] == i


def test_13_domain_separation():
    locs = vd.load_locations()
    spec = resolve_scene_environment("en", SCENES["en"][0], locations=locs)
    d = spec.to_dict()
    assert assert_domain_separation(d) == []
    assert "identity" in (d.get("observability") or {}).get("excluded_domains", [])


def test_14_observability_per_still():
    pkg = vd.build_visual_scene_package("en", "1", SCENES["en"][0])
    for sh in pkg.get("shots") or []:
        obs = sh.get("scene_environment_observability") or {}
        assert obs.get("authority")
        assert "still_index" in obs
        assert obs.get("domain") == "scene_environment"
    assert "scene_environment" in pkg


def test_15_no_novel_borrow_en_into_ha():
    locs = vd.load_locations()
    loc = match_studio_bible_location("apartment kitchen counter", locs, "ha")
    assert loc is None


def test_16_aivsb_still_diff_fragments_unique():
    frags = [
        still_differentiation_fragment(
            "ha", SCENES["ha"][i], still_index=i, still_role=("establishing", "travel", "climax")[i],
            composition_goal=SCENES["ha"][i],
        )
        for i in range(3)
    ]
    assert len(set(frags)) == 3
    assert all("STILL_INDEX=" in f for f in frags)
    assert all("COMPOSITION_GOAL=" in f for f in frags)


def test_17_aivsb_compose_identical_rate_zero(monkeypatch):
    monkeypatch.setenv("AIVSB_REASONING_ENABLED", "1")
    import app as app_mod

    chars = {"ha": "Kai", "en": "Kael", "hp": "Liang", "sf": "Jarek"}
    pair_id = 0
    pair_tot = 0
    for novel, scenes in SCENES.items():
        prompts = []
        for i, beat in enumerate(scenes):
            out = app_mod.compose_aivsb_scene_prompt(
                novel, beat, chars[novel],
                platform="youtube_short", asset_type="chapter_still", orientation="vertical",
                legacy_prompt="", still_index=i,
                still_role=("establishing", "travel", "climax")[i],
                composition_goal=beat,
            )
            assert out and out.get("prompt")
            prompts.append(out["prompt"])
            assert "STILL_INDEX=" in out["prompt"]
            # provenance fields preserved
            assert "bible_version" in out
            assert "applied_rule_ids" in out
        for a in range(len(prompts)):
            for b in range(a + 1, len(prompts)):
                pair_tot += 1
                if prompts[a] == prompts[b]:
                    pair_id += 1
    assert pair_tot > 0
    assert pair_id == 0


def test_18_cross_novel_leak_count_zero_matrix():
    leak = 0
    for novel, scenes in SCENES.items():
        if novel == "hp":
            continue
        for i, s in enumerate(scenes):
            pkg = vd.build_visual_scene_package(novel, str(i + 1), s)
            blob = _blob_pkg(pkg).lower()
            for lm in ("ruined sect hall", "jade altar"):
                if lm in blob:
                    leak += 1
    assert leak == 0


def test_19_composition_fail_zero():
    fails = 0
    for novel, scenes in SCENES.items():
        bundles = set()
        for i, s in enumerate(scenes):
            pkg = vd.build_visual_scene_package(novel, str(i + 1), s)
            cams = "||".join(sh.get("camera", "") for sh in (pkg.get("shots") or []))
            bundles.add(cams)
        if len(bundles) < len(scenes):
            fails += 1
    assert fails == 0


def test_20_location_fail_zero_for_mapped():
    """EN/SF/HP representative scenes must resolve; HA apartment may be UNSPECIFIED."""
    fails = 0
    locs = vd.load_locations()
    expect = {
        "en": "en_nexus_city",
        "sf": "sf_forge",
        "hp": "hp_sect",
    }
    for novel, loc_id in expect.items():
        loc = match_studio_bible_location(SCENES[novel][0], locs, novel)
        if not loc or loc.get("id") != loc_id:
            fails += 1
    assert fails == 0


def test_21_cpu_matrix_package_prompt_counts():
    packages = 0
    prompts = 0
    for novel, scenes in SCENES.items():
        for i, s in enumerate(scenes):
            pkg = vd.build_visual_scene_package(novel, str(i + 1), s)
            packages += 1
            prompts += len(pkg.get("image_prompts") or [])
    assert packages >= 12
    assert prompts >= 36


def test_22_frozen_lanes_untouched_flags():
    # Remediation must not introduce a new required ON flag; identity default OFF in source.
    # Spot-check: scene_environment module has no identity/wardrobe enablement side effects.
    import tools.scene_environment as se
    src = Path(se.__file__).read_text(encoding="utf-8")
    assert "ENABLE_IDENTITY_PRESERVATION" not in src or "excluded_domains" in src
    assert "ENABLE_WARDROBE_PRESERVATION" not in src.split("excluded_domains")[0]
    # No new SCENE_ENV enablement flag required
    assert "ENABLED_SCENE_ENVIRONMENT" not in src


if __name__ == "__main__":
    import traceback

    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as exc:
            failed += 1
            print("FAIL", name, exc)
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
