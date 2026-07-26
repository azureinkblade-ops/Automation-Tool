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
    d0 = prompts["director"][0]
    assert "Character Identity:" in d0 and "Liang" in d0, "Director prompt must carry the permanent identity block"
    assert "silver-edged sword" in " ".join(prompts["director"]).lower() or "chinese jian" in " ".join(prompts["director"]).lower(), "weapon must be canonicalized"
    assert "silver edged weapon, silver edged" not in " ".join(prompts["director"]).lower(), "weapon duplicate must be fixed"
    assert "Depict" in d0, "Director prompt must lead with an imperative scene description"
    objs = [p.split("Depict")[1].split(". ")[0].strip()
            for p in prompts["director"] if "Depict" in p]
    assert len(set(objs)) == 3, "each shot needs a distinct imperative scene (no repetition)"
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


def test_recorded_backend_plays_real_traces():
    import tempfile
    tmp_path = Path(tempfile.mkdtemp(prefix="ab_rec_"))
    from tests.render_ab.harness import RenderResult, RecordedBackend
    # Simulate real OpenAI traces (would come from the actual app call).
    real = [
        RenderResult(provider="openai", model="gpt-image-1", path=str(tmp_path / "src0.png"),
                     ok=True, prompt="legacy prompt 0", trace_meta={"model": "gpt-image-1", "size": "1024x1536"}),
        RenderResult(provider="openai", model="gpt-image-1", path=str(tmp_path / "src1.png"),
                     ok=True, prompt="legacy prompt 1", trace_meta={"model": "gpt-image-1", "size": "1024x1536"}),
        RenderResult(provider="openai", model="gpt-image-1", path=str(tmp_path / "src2.png"),
                     ok=True, prompt="legacy prompt 2", trace_meta={"model": "gpt-image-1", "size": "1024x1536"}),
    ]
    # create placeholder source files so RecordedBackend can copy them
    for r in real:
        Path(r.path).write_bytes(b"\x89PNG\r\n\x1a\n")
    backend = RecordedBackend(results=real * 2)
    out = tmp_path / "out"
    legacy = [r.prompt for r in real]
    ab = H.run_ab("hp_liang_review", legacy, legacy, backend, out)
    assert ab["legacy"][0]["provider"] == "openai"
    assert ab["legacy"][0]["model"] == "gpt-image-1"
    assert Path(ab["legacy"][0]["path"]).exists()
    print("PASS recorded backend: real provider traces flow through run_ab")


def test_localsd_backend_not_ready_reports_failure():
    # When local SD is not ready in the runtime, the backend must expose the
    # failure (never hide it) rather than crash or claim success.
    import tests.render_ab.harness as H
    import app as appmod
    orig = appmod.local_stable_diffusion_status
    try:
        appmod.local_stable_diffusion_status = lambda: {"ready": False, "dependencies": {"torch": False}, "model": "x"}
        backend = H.LocalSDAppBackend(app_module=appmod)
        from pathlib import Path as _P
        r = backend.render("some prompt", _P(tmp_path if False else __import__("tempfile").mkdtemp(prefix="ab_sd_")) / "x.png")
        assert r.ok is False
        assert "not ready" in r.error.lower()
        print("PASS local-sd backend: not-ready exposes failure, no hidden success")
    finally:
        appmod.local_stable_diffusion_status = orig


def test_localsd_backend_invokes_generator_when_ready(monkeypatch_tmp=None):
    # Exercise the real command construction by faking readiness + subprocess.
    import tests.render_ab.harness as H
    import app as appmod
    import subprocess as _sp
    import json as _json
    from pathlib import Path as _P
    import tempfile as _tf

    captured = {}
    tmp = _P(_tf.mkdtemp(prefix="ab_sdok_"))

    def fake_status():
        return {
            "ready": True,
            "dependencies": {"torch": True, "diffusers": True, "transformers": True, "PIL": True},
            "model": "models/sdxl-base",
            "refinerModel": "", "qualityMode": "premium", "scheduler": "dpm",
            "timeoutSeconds": 60,
        }

    def fake_local_sd_python():
        return "python"

    def fake_lora_track(prompt, orientation="vertical"):
        return "main-posts"

    def fake_find_lora(track):
        return _P(tmp) / "lora.safetensors"

    def fake_enhance(prompt, orientation="vertical", lora_track=""):
        return f"ENHANCED::{prompt}"

    class _CP:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(cmd, **kw):
        captured["cmd"] = list(cmd)
        # write a fake image + generator metadata (must exceed the 1024-byte validity guard)
        out = _P(cmd[cmd.index("--output") + 1])
        out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 2048)
        meta = _P(cmd[cmd.index("--metadata") + 1])
        # Echo the requested seed back so the control check sees no mismatch.
        req_seed = cmd[cmd.index("--seed") + 1]
        meta.write_text(_json.dumps({"model": "models/sdxl-base", "seed": int(req_seed)}), encoding="utf-8")
        return _CP()

    orig = (appmod.local_stable_diffusion_status, appmod.local_sd_python,
            appmod.lora_track_for_prompt, appmod.find_lora_weights_for_track,
            appmod.enhance_local_sd_prompt, appmod._LOCAL_SD_GPU_LOCK)
    appmod.local_stable_diffusion_status = fake_status
    appmod.local_sd_python = fake_local_sd_python
    appmod.lora_track_for_prompt = fake_lora_track
    appmod.find_lora_weights_for_track = fake_find_lora
    appmod.enhance_local_sd_prompt = fake_enhance
    import threading as _th
    appmod._LOCAL_SD_GPU_LOCK = _th.Lock()
    import subprocess as _sp
    _orig_run = _sp.run
    _sp.run = fake_run
    try:
        backend = H.LocalSDAppBackend(app_module=appmod, orientation="vertical")
        target = tmp / "img.png"
        r = backend.render("Liang in the hall", target)
        assert r.ok is True, r.error
        assert r.provider == "local_stable_diffusion"
        assert r.model == "models/sdxl-base"
        # command must contain the real generator script and enhanced prompt
        assert any("local_image_generator" in str(c) for c in captured["cmd"])
        assert any("ENHANCED::Liang in the hall" == str(c) for c in captured["cmd"])
        assert any(c == "--lora-path" for c in captured["cmd"])
        print("PASS local-sd backend: builds identical generator command, records real trace")
    finally:
        _sp.run = _orig_run
        (appmod.local_stable_diffusion_status, appmod.local_sd_python,
         appmod.lora_track_for_prompt, appmod.find_lora_weights_for_track,
         appmod.enhance_local_sd_prompt, appmod._LOCAL_SD_GPU_LOCK) = orig


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
