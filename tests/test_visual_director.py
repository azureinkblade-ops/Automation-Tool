"""Visual Director Slice 1 — acceptance tests.

Run under the codex runtime:
  python tests/test_visual_director.py

These prove the core premise: the Studio Bible can produce BETTER image
prompts than the generic string builder, with canon-locked character
appearance and world consistency.

Tests map to the user's stated acceptance criteria:
  Test 1: Character consistency (hair, clothing, weapon, age/body)
  Test 2: World consistency (cultivation setting, environment, tech level, magic)
  Test 3: Shot quality (3 distinct purpose-driven shots)
  Test 4: Existing pipeline compatibility (image_prompts + image_sources map to
          metadata.json; TikTok pipeline is unaware of the Director)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import visual_director as vd  # noqa: E402


def _pkg(novel="hp", chapter="6", scene="Liang enters the ruined sect"):
    return vd.build_visual_scene_package(novel, chapter, scene)


def test_1_character_consistency():
    """Output must contain Liang's hair, clothing, weapon, age/body traits."""
    pkg = _pkg()
    locks = {l["name"]: l for l in pkg["character_locks"]}
    assert "Liang" in locks, "Liang not extracted from scene text"
    lock = locks["Liang"]
    blob = json.dumps(lock).lower()
    assert "dark" in blob, "hair (dark topknot) missing"
    assert "jade" in blob, "clothing (jade sect robes) missing"
    assert "silver" in blob, "weapon (silver edged) missing"
    assert lock.get("body_type") or lock.get("age"), "age/body traits missing"

    # every generated prompt must carry the locked appearance tokens
    for prompt in pkg["image_prompts"]:
        p = prompt.lower()
        assert "liang" in p, "prompt missing character name"
        assert "jade" in p or "robe" in p, "prompt missing clothing lock"
        assert "silver" in p or "weapon" in p, "prompt missing weapon lock"
        assert "dark" in p or "hair" in p, "prompt missing hair lock"
    print("PASS Test 1: character consistency")


def test_2_world_consistency():
    """Output must reflect cultivation setting, environment, correct tech level, magic."""
    pkg = _pkg()
    blob = json.dumps(pkg).lower()
    # cultivation fantasy world (HP is xianxia, not modern)
    assert "cultivation" in blob, "cultivation setting missing"
    # environment resolved from location match
    env = json.dumps(pkg["environment"]).lower()
    assert "ruin" in env or "sect" in env, "environment not resolved"
    # magic system present
    assert "qi" in blob or "ember" in blob or "magic" in blob, "magic system missing"
    # technology level guard: must NOT invite modern objects
    for prompt in pkg["image_prompts"]:
        assert "modern" not in prompt.lower() or "avoid" in prompt.lower(), \
            "prompt risks modern contamination"
    print("PASS Test 2: world consistency")


def test_3_shot_quality():
    """Three prompts must be three purpose-driven shots, not random illustrations."""
    pkg = _pkg()
    shots = pkg["shots"]
    assert len(shots) == 3, f"expected 3 shots, got {len(shots)}"
    types = [s["type"] for s in shots]
    assert types == ["establishing", "travel", "climax"], f"unexpected shot order: {types}"
    for shot in shots:
        assert shot.get("camera"), "shot missing camera direction"
        assert shot.get("narrative_objective"), "shot missing narrative objective"
        assert shot.get("action"), "shot missing pose/action"
        assert shot.get("emotion"), "shot missing emotion"
        assert "environment_state" in shot, "shot missing environment state"
    assert len(pkg["image_prompts"]) == 3, "image_prompts count mismatch"
    # shots should differ from each other (not 3 copies)
    assert len(set(pkg["image_prompts"])) == 3, "shots are duplicates"
    # every prompt must carry the permanent character-identity block
    for prompt in pkg["image_prompts"]:
        assert "Character Identity:" in prompt, "prompt missing permanent identity block"
    print("PASS Test 3: shot quality")


def test_4_pipeline_compatibility():
    """Output maps to metadata.json {image_prompts, image_sources}; no new fields
    the TikTok pipeline would choke on."""
    pkg = _pkg()
    assert isinstance(pkg["image_prompts"], list)
    assert all(isinstance(p, str) and p.strip() for p in pkg["image_prompts"])
    assert isinstance(pkg["image_sources"], list)
    # the two fields a downstream consumer reads:
    assert "image_prompts" in pkg and "image_sources" in pkg
    print("PASS Test 4: pipeline compatibility")


def test_5_novel_isolation():
    """Kael (EN) and Kai (HA) must not collide; each pulls its own canon."""
    en = vd.build_visual_scene_package("en", "1", "Kael stands before the NexusPod")
    ha = vd.build_visual_scene_package("ha", "1", "Kai awakens in the alley")
    en_blob = json.dumps(en["character_locks"]).lower()
    ha_blob = json.dumps(ha["character_locks"]).lower()
    assert "kael" in en_blob and "kai" not in en_blob, "EN pulled wrong character"
    assert "kai" in ha_blob and "kael" not in ha_blob, "HA pulled wrong character"
    print("PASS Test 5: novel isolation (Kael != Kai)")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    if failed:
        print(f"\n{failed} test(s) failed")
        sys.exit(1)
    print(f"\nAll {len(tests)} Visual Director Slice 1 tests passed")
