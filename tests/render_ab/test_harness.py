"""Tests for the rendered A/B harness using a mocked (free, offline) backend.

These tests exercise the full orchestration + evaluation path WITHOUT any
external-provider / cost-bearing call. Generation is driven by MockBackend.
The real generation step (RecordedBackend + operator-supplied traces) is kept
out of CI and behind explicit cost authorization.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
import tests.render_ab.harness as H  # noqa: E402


def _scene():
    return (
        "The Hundredfold Path", "chapter text",
        ["Liang enters the ruined sect hall",
         "He climbs the broken stair toward the jade altar",
         "Silver light wakes the dormant formation"],
        "hp",
    )


def test_capture_prompts_real_legacy_and_director():
    title, chapter, phrases, novel = _scene()
    prompts = H.capture_prompts(title, chapter, phrases, novel, appmod)
    assert set(prompts) == {"legacy", "director"}
    assert len(prompts["legacy"]) == 3 and len(prompts["director"]) == 3
    # legacy is the generic template; director is canon-locked
    assert prompts["legacy"][0].startswith("Vertical 9:16 cinematic fantasy web novel cover art")
    assert "Subject:" in prompts["director"][0] and "Liang" in prompts["director"][0]
    print("PASS capture: 3 legacy + 3 director prompts from real app path")


def test_run_ab_generates_six_new_images():
    import tempfile
    tmp_path = Path(tempfile.mkdtemp(prefix="ab_run_"))
    title, chapter, phrases, novel = _scene()
    prompts = H.capture_prompts(title, chapter, phrases, novel, appmod)
    out = tmp_path / "ab_out"
    ab = H.run_ab("hp_liang_review", prompts["legacy"], prompts["director"], H.MockBackend(), out)
    assert len(ab["legacy"]) == 3 and len(ab["director"]) == 3
    for kind in ("legacy", "director"):
        for r in ab[kind]:
            assert r["ok"] is True
            assert r["cached"] is False  # A/B requires fresh assets
            assert Path(r["path"]).exists() and Path(r["path"]).stat().st_size > 0
    assert (out / "legacy" / "legacy_0.png").exists()
    assert (out / "visual-director" / "director_0.png").exists()
    print("PASS run_ab: 6 new images, no cache reuse, separate dirs")


def test_manifest_and_report_written():
    import tempfile
    tmp_path = Path(tempfile.mkdtemp(prefix="ab_man_"))
    title, chapter, phrases, novel = _scene()
    prompts = H.capture_prompts(title, chapter, phrases, novel, appmod)
    ab = H.run_ab("hp_liang_review", prompts["legacy"], prompts["director"], H.MockBackend(), tmp_path / "out")
    legacy_score = H.build_score(
        {c: 3 for c in H.CRITERIA},
        [{"liang_recognizable": True, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    director_score = H.build_score(
        {c: 4 for c in H.CRITERIA},
        [{"liang_recognizable": True, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    gate = H.evaluate_gate(legacy_score, director_score)
    H.write_manifest(tmp_path / "manifest.json", {"scene_id": "hp_liang_review", "ab": ab, "prompts": prompts})
    H.write_report(tmp_path / "report.md", "hp_liang_review", prompts, ab, legacy_score, director_score, gate)
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "report.md").exists()
    data = __import__("json").loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert data["scene_id"] == "hp_liang_review"
    assert "legacy" in data["ab"] and "director" in data["ab"]
    print("PASS manifest+report: artifacts written with prompts + traces + scores")


def test_gate_requires_real_win_not_tie():
    legacy = H.build_score(
        {"character_identity": 3, "canon_accuracy": 3, "shot_differentiation": 4,
         "sequence_coherence": 3, "mobile_readability": 3, "artifact_control": 4, "overall_improvement": 3},
        [{"liang_recognizable": True, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    director = H.build_score(
        {"character_identity": 3, "canon_accuracy": 3, "shot_differentiation": 4,
         "sequence_coherence": 3, "mobile_readability": 3, "artifact_control": 4, "overall_improvement": 3},  # tie
        [{"liang_recognizable": True, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    gate = H.evaluate_gate(legacy, director)
    assert gate["recommend_continue"] is False, "a tie must not pass the gate"
    assert gate["director_wins"] is False
    print("PASS gate: tie rejected")


def test_gate_fails_on_canon_regression():
    legacy = H.build_score(
        {"character_identity": 3, "canon_accuracy": 4, "shot_differentiation": 4,
         "sequence_coherence": 3, "mobile_readability": 3, "artifact_control": 4, "overall_improvement": 3},
        [{"liang_recognizable": True, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    director = H.build_score(
        {"character_identity": 3, "canon_accuracy": 2, "shot_differentiation": 4,  # regression
         "sequence_coherence": 3, "mobile_readability": 3, "artifact_control": 4, "overall_improvement": 5},
        [{"liang_recognizable": True, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    gate = H.evaluate_gate(legacy, director)
    assert gate["recommend_continue"] is False
    assert gate["canon_no_regression"] is False
    print("PASS gate: canon regression rejected even if overall wins")


def test_gate_passes_on_clear_win():
    legacy = H.build_score(
        {"character_identity": 2, "canon_accuracy": 2, "shot_differentiation": 2,
         "sequence_coherence": 2, "mobile_readability": 3, "artifact_control": 3, "overall_improvement": 2},
        [{"liang_recognizable": True, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    director = H.build_score(
        {"character_identity": 4, "canon_accuracy": 4, "shot_differentiation": 5,
         "sequence_coherence": 4, "mobile_readability": 4, "artifact_control": 4, "overall_improvement": 5},
        [{"liang_recognizable": True, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    gate = H.evaluate_gate(legacy, director)
    assert gate["recommend_continue"] is True
    print("PASS gate: clear win recommended")


def test_harness_does_not_touch_production():
    import tempfile
    tmp_path = Path(tempfile.mkdtemp(prefix="ab_iso_"))
    title, chapter, phrases, novel = _scene()
    prompts = H.capture_prompts(title, chapter, phrases, novel, appmod)
    out = tmp_path / "ab_out"
    H.run_ab("hp_liang_review", prompts["legacy"], prompts["director"], H.MockBackend(), out)
    for f in out.rglob("*.png"):
        assert str(tmp_path) in str(f), "output must stay in the test sandbox"
    print("PASS isolation: outputs confined to test sandbox")


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
    print(f"\nAll {len(tests)} A/B harness tests passed")
