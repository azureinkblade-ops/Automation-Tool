"""Integration test: Visual Director wiring into make_chapter_image_prompts.

Scope: this test ONLY verifies the env-gated integration (commit scope). It does
NOT touch AIVSB, providers, metadata schema, or video consumers. It asserts:

OFF (default / false / unset):
  - existing behavior is preserved (returns 3 legacy generic prompts)
  - output is identical to running with the flag explicitly off
ON (VISUAL_DIRECTOR_ENABLED=true):
  - Visual Director prompts returned
  - prompt count preserved (3)
  - Liang canon tokens present (HP)
  - Kael/Kai novel isolation preserved (EN vs HA)
  - malformed/incomplete Bible data does not crash generation

Fail-soft:
  - missing Bible path -> legacy prompts returned, workflow continues

Run under the codex runtime from the repo root:
  python tests/test_visual_director_integration.py
"""

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Make sure we import the repo's app.py (not a stray module).
import app as appmod  # noqa: E402


def _call(title, chapter, phrases, novel, env_value, aivsb="off"):
    """Call make_chapter_image_prompts with specific VISUAL_DIRECTOR + AIVSB env
    settings. AIVSB is forced OFF in these tests so the Director's contract is
    isolated from the (separate, frozen) AIVSB reasoning flag. The Director
    branch is checked BEFORE the AIVSB branch and returns early, so the two
    flags are independent; forcing AIVSB off here just makes the OFF-path
    baseline the true legacy generic string.
    """
    prev_vd = os.environ.get("VISUAL_DIRECTOR_ENABLED")
    prev_aivsb = os.environ.get("AIVSB_REASONING_ENABLED")
    if env_value is None:
        os.environ.pop("VISUAL_DIRECTOR_ENABLED", None)
    else:
        os.environ["VISUAL_DIRECTOR_ENABLED"] = env_value
    os.environ["AIVSB_REASONING_ENABLED"] = aivsb
    try:
        return appmod.make_chapter_image_prompts(title, chapter, phrases, novel)
    finally:
        if prev_vd is None:
            os.environ.pop("VISUAL_DIRECTOR_ENABLED", None)
        else:
            os.environ["VISUAL_DIRECTOR_ENABLED"] = prev_vd
        if prev_aivsb is None:
            os.environ.pop("AIVSB_REASONING_ENABLED", None)
        else:
            os.environ["AIVSB_REASONING_ENABLED"] = prev_aivsb


def test_off_default_is_legacy():
    phrases = ["Liang enters the ruined sect", "He climbs the broken stair", "Silver light wakes"]
    out_unset = _call("The Hundredfold Path", "chapter text here", phrases, "hp", None)
    out_false = _call("The Hundredfold Path", "chapter text here", phrases, "hp", "false")
    out_off = _call("The Hundredfold Path", "chapter text here", phrases, "hp", "off")
    for out in (out_unset, out_false, out_off):
        assert isinstance(out, list) and len(out) == 3, f"expected 3 prompts, got {out!r}"
        # legacy generic template markers
        assert out[0].startswith("Vertical 9:16 cinematic fantasy web novel cover art"), \
            "OFF path must produce the legacy generic prompt"
        assert "Subject:" not in out[0], "OFF path must NOT contain Director Subject lock"
    # default (unset) must equal explicit off (byte-identical behavior)
    assert out_unset == out_off, "unset must equal explicit off"
    print("PASS test_off_default_is_legacy: OFF path byte-identical to legacy")


def test_on_returns_director_prompts():
    phrases = ["Liang enters the ruined sect", "He climbs the broken stair", "Silver light wakes"]
    out = _call("The Hundredfold Path", "chapter text here", phrases, "hp", "true")
    assert isinstance(out, list) and len(out) == 3, f"expected 3 Director prompts, got {out!r}"
    assert out[0].startswith("xianxia cultivation fantasy illustration"), \
        "ON path must return Director genre-labeled prompt"
    assert "Character Identity:" in out[0] and "Liang" in out[0], "Liang character lock must be present"
    assert "Depict" in out[0], "Director prompt must lead with an imperative scene description"
    # per-image imperative scene must differ across the 3 shots (no repetition)
    objectives = [p.split("Depict")[1].split(". ")[0].strip() for p in out if "Depict" in p]
    assert len(objectives) == 3, "expected an imperative scene per shot"
    assert len(set(objectives)) == 3, "imperative scenes must differ across shots (no repetition)"
    # weapon must be canonicalized + deduped (no 'silver edged weapon, silver edged')
    blob = " ".join(out).lower()
    assert "jade" in blob, "Liang clothing (jade) missing"
    assert "silver-edged sword" in blob or "chinese jian" in blob, "Liang weapon not canonicalized to a precise sword lock"
    assert "silver edged weapon, silver edged" not in blob, "weapon duplicate not fixed"
    assert "dark" in blob or "hair" in blob, "Liang hair missing"
    print("PASS test_on_returns_director_prompts: ON path returns canon-locked prompts")


def test_on_novel_isolation():
    en = _call("Eternal Nexus", "chapter text", ["Kael stands before the NexusPod"], "en", "true")
    ha = _call("Heavenly Ascension System", "chapter text", ["Kai awakens in the alley"], "ha", "true")
    en_blob = " ".join(en).lower()
    ha_blob = " ".join(ha).lower()
    assert "kael" in en_blob and "kai" not in en_blob, "EN leaked wrong character"
    assert "kai" in ha_blob and "kael" not in ha_blob, "HA leaked wrong character"
    print("PASS test_on_novel_isolation: Kael (EN) != Kai (HA) in integrated path")


def test_failsoft_missing_bible():
    """If the Bible path is absent, ON path must fall back to legacy and not crash."""
    # Point the Director at a nonexistent Bible dir, force ON, expect legacy output.
    import visual_director as vd
    prev = vd.BIBLE_DIR
    vd.BIBLE_DIR = Path(r"C:\nonexistent\bible\path")
    try:
        out = _call("The Hundredfold Path", "chapter text", ["Liang enters the ruined sect"], "hp", "true")
    finally:
        vd.BIBLE_DIR = prev
    assert isinstance(out, list) and len(out) == 3, "fail-soft must still return 3 prompts"
    assert out[0].startswith("Vertical 9:16 cinematic fantasy web novel cover art"), \
        "missing Bible must fall back to legacy generic prompt"
    print("PASS test_failsoft_missing_bible: missing Bible -> legacy, no crash")


def test_failsoft_builder_raises():
    """If the package builder raises, ON path must fall back to legacy."""
    import visual_director as vd
    real_fn = vd.build_visual_scene_package

    def _boom(*a, **k):
        raise RuntimeError("simulated Director failure")

    vd.build_visual_scene_package = _boom
    try:
        out = _call("The Hundredfold Path", "chapter text", ["Liang enters the ruined sect"], "hp", "true")
    finally:
        vd.build_visual_scene_package = real_fn
    assert isinstance(out, list) and len(out) == 3, "builder raise must fall back to legacy"
    assert out[0].startswith("Vertical 9:16 cinematic fantasy web novel cover art"), \
        "builder raise must fall back to legacy generic prompt"
    print("PASS test_failsoft_builder_raises: builder exception -> legacy, no crash")


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
    print(f"\nAll {len(tests)} Visual Director integration tests passed")
