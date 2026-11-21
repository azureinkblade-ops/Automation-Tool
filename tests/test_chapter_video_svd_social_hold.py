"""SVD-only chapter clips are held for social (MEDIA_HOLD / SVD_FALLBACK_SOCIAL_HOLD); Wan stays SOCIAL_READY.

Decision (2026-11-21): when Wan fails and SVD succeeds (or SVD is the chosen backend), the clip is never
SOCIAL_READY, so Social never sees it as ready to post. The hold is social/video only: the Patreon and Royal Road
text releases go out as planned (they never read the Reel pack). The result records what the clip is: backend,
fps (raw SVD: 25 frames @ 6 fps, 1024x576; presented 1080x1920) and fallback_restart.

CPU only: fake pipelines / probes / launcher; ComfyUI is never contacted, app.py is imported in the test sandbox.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import warnings
from pathlib import Path

import pytest

from tools import chapter_video_wiring as cvw
from tests.test_chapter_video_wiring import CFG, _drive, app_env  # noqa: F401  (app_env is a fixture)

REPO = Path(__file__).resolve().parents[1]
SVD_HELD = "SVD_FALLBACK_SOCIAL_HOLD"
META_KEYS = {"backend", "fps", "fallback_restart", "fallback_used", "raw_frame_count", "raw_fps", "raw_width",
             "raw_height", "output_width", "output_height", "output_frame_count", "output_fps", "duration_seconds",
             "social_status", "social_hold", "hold_reason"}


# --------------------------------------------------------------------------- wiring (result level)

def test_svd_fallback_is_held_for_social_not_social_ready(tmp_path, monkeypatch):
    res, log, _ = _drive(tmp_path, {"wan_22": "hold", "svd_xt_1_1": "ok"}, monkeypatch, duration=25 / 6)
    assert [b for b, *_ in log] == ["wan_22", "svd_xt_1_1"]
    assert res.outcome == "MEDIA_HOLD" and res.outcome != cvw.SOCIAL_READY
    assert res.hold_reason == SVD_HELD == cvw.SVD_FALLBACK_SOCIAL_HOLD
    assert res.social_hold and not res.ready and res.clip_produced
    assert res.backend_used == "svd_xt_1_1" and res.fallback_used
    assert res.asset_path and Path(res.asset_path).is_file()  # kept for review, never posted


def test_svd_hold_metadata_backend_fps_and_fallback_restart(tmp_path, monkeypatch):
    res, _, _ = _drive(tmp_path, {"wan_22": "hold", "svd_xt_1_1": "ok"}, monkeypatch, duration=25 / 6)
    m = res.clip_metadata
    assert META_KEYS <= set(m)
    assert m["backend"] == "svd_xt_1_1" and m["fps"] == 6 and m["raw_fps"] == 6 and m["raw_frame_count"] == 25
    assert (m["raw_width"], m["raw_height"]) == (1024, 576)
    assert (m["output_width"], m["output_height"]) == (1080, 1920)
    assert m["fallback_restart"] == "" and m["fallback_used"] is True
    assert m["social_status"] == "MEDIA_HOLD" and m["social_hold"] is True and m["hold_reason"] == SVD_HELD
    # the same metadata rides on the successful attempt, which app.py copies into metadata["mediaHold"]["attempts"]
    clip = res.attempts[-1]["clip"]
    assert clip["backend"] == "svd_xt_1_1" and clip["fps"] == 6 and "fallback_restart" in clip
    assert clip["asset_path"] == res.asset_path and clip["asset_sha256"] == res.asset_sha256


def test_svd_after_restart_is_recorded_in_metadata():
    clip = cvw.ChapterClipResult(outcome=cvw.SOCIAL_READY, asset_path="x.mp4", backend_used="svd_xt_1_1",
                                 fallback_used=True, width=1080, height=1920, frame_count=100, duration_seconds=4.17,
                                 fallback_restart=cvw.FALLBACK_RESTART_OK)
    attempt = {"backend": "svd_xt_1_1", "outcome": "SOCIAL_READY"}
    out = cvw.finalize_clip_result(CFG, clip, attempt)
    assert out.outcome == "MEDIA_HOLD" and out.hold_reason == SVD_HELD and out.social_hold
    assert out.clip_metadata["fallback_restart"] == "svd_after_restart" == attempt["clip"]["fallback_restart"]
    assert out.clip_metadata["output_fps"] == round(100 / 4.17, 3)


def test_svd_only_switch_is_also_held(tmp_path, monkeypatch):
    cfg = dataclasses.replace(cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_BACKEND": "svd_xt_1_1"}), idle_restart=False)
    res, log, _ = _drive(tmp_path, {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch, cfg=cfg, duration=25 / 6)
    assert [b for b, *_ in log] == ["svd_xt_1_1"]
    assert res.outcome == "MEDIA_HOLD" and res.hold_reason == SVD_HELD and not res.ready and not res.fallback_used


def test_wan_result_is_still_social_ready_exactly_as_before(tmp_path, monkeypatch):
    res, log, _ = _drive(tmp_path, {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch)
    assert [b for b, *_ in log] == ["wan_22"]
    assert res.outcome == cvw.SOCIAL_READY and res.ready and res.hold_reason is None and not res.social_hold
    m = res.clip_metadata
    assert META_KEYS <= set(m)
    assert m["backend"] == "wan_22" and m["fps"] == 24 and m["raw_frame_count"] == 73
    assert (m["raw_width"], m["raw_height"]) == (720, 1280)
    assert m["social_status"] == "SOCIAL_READY" and m["social_hold"] is False and m["hold_reason"] == ""


def test_both_backends_failing_is_unchanged_video_required_missing(tmp_path, monkeypatch):
    res, _, _ = _drive(tmp_path, {"wan_22": "hold", "svd_xt_1_1": "hold"}, monkeypatch)
    assert res.outcome == "MEDIA_HOLD" and res.hold_reason.startswith("VIDEO_REQUIRED_MISSING:")
    assert not res.social_hold and res.asset_path is None and res.clip_metadata == {}


# --------------------------------------------------------------------------- app.py (Reel pack level)

def _svd_held_result(tmp_path, monkeypatch):
    res, _, _ = _drive(tmp_path / "drive", {"wan_22": "hold", "svd_xt_1_1": "ok"}, monkeypatch, duration=25 / 6)
    return res


def test_app_reel_pack_with_svd_clip_is_held_and_social_gate_blocks(app_env, tmp_path, monkeypatch):
    app_mod, folder = app_env
    (tmp_path / "drive").mkdir()
    held = _svd_held_result(tmp_path, monkeypatch)
    monkeypatch.setattr(cvw, "produce_chapter_clip", lambda still, **kw: held)
    build = app_mod.build_reel_motion_video(folder)
    assert build["created"] is False and build["media_hold"] is True and build["message"] == SVD_HELD
    assert not (folder / "tiktok-video.mp4").exists()  # Social has nothing to post
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert meta["mediaHold"]["status"] == "MEDIA_HOLD" and meta["mediaHold"]["reason"] == SVD_HELD
    assert "motion_clip" not in meta
    clip = meta["mediaHold"]["attempts"][-1]["clip"]  # what the clip is, visible to Product Performance / Social
    assert clip["backend"] == "svd_xt_1_1" and clip["fps"] == 6 and "fallback_restart" in clip
    errs = app_mod.chapter_video_wire_gate_errors(folder, meta)
    assert errs and errs[0].startswith("MEDIA_HOLD: " + SVD_HELD)


def test_app_reel_pack_with_wan_clip_stays_ready(app_env, tmp_path, monkeypatch):
    app_mod, folder = app_env
    (tmp_path / "drive").mkdir()
    res, _, _ = _drive(tmp_path / "drive", {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch)
    monkeypatch.setattr(cvw, "produce_chapter_clip", lambda still, **kw: res)
    monkeypatch.setattr(app_mod, "media_duration_seconds", lambda p: 73 / 24)
    monkeypatch.setattr(cvw, "verify_motion_clip", lambda p, m, **k: (True, "ok") if (m or {}).get("asset_sha256") == hashlib.sha256(Path(p).read_bytes()).hexdigest() else (False, "sha256_mismatch"))
    build = app_mod.build_reel_motion_video(folder)
    assert build["created"] and not build["media_hold"] and build["backend"] == "wan_22"
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert "mediaHold" not in meta and meta["motion_clip"]["backend"] == "wan_22"
    assert app_mod.chapter_video_wire_gate_errors(folder, meta) == []


# --------------------------------------------------------------------------- text release is not blocked

def _app_graph():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        src = (REPO / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
    fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    graph = {k: {x.id for x in ast.walk(v) if isinstance(x, ast.Name) and x.id in fns} for k, v in fns.items()}
    return src, fns, graph


def _reachable(graph, roots):
    seen, stack = set(), list(roots)
    while stack:
        f = stack.pop()
        if f not in seen:
            seen.add(f)
            stack.extend(graph.get(f, ()))
    return seen


def test_text_release_never_builds_or_reads_the_reel_clip():
    """The release worker (Patreon tiers + Royal Road) never builds the Reel clip or reads its result."""
    _, fns, graph = _app_graph()
    roots = ["run_release_automation_job", "release_stage_completion_gate", "mark_chapter_release_stage_complete"]
    assert all(r in fns for r in roots)
    reach = _reachable(graph, roots)
    for reel_only in ("build_reel_motion_video", "rebuild_normal_tiktok_video_from_metadata", "ensure_buffer_video",
                      "chapter_video_wire_applies"):
        assert reel_only not in reach, reel_only


def test_reel_hold_gate_only_applies_to_reel_pack_folders():
    """The one shared function (folder_quality_gate) applies the Reel hold only inside the tiktok-posts branch,
    and the release worker's preview refuses tiktok-posts folders, so a Reel MEDIA_HOLD can't block text."""
    src, fns, _ = _app_graph()
    callers = [name for name, fn in fns.items()
               if any(isinstance(x, ast.Call) and getattr(x.func, "id", "") == "chapter_video_wire_gate_errors"
                      for x in ast.walk(fn))]
    assert callers == ["folder_quality_gate"]
    gate = fns["folder_quality_gate"]
    branch = next(n for n in ast.walk(gate) if isinstance(n, ast.If) and isinstance(n.test, ast.Name)
                  and n.test.id == "is_tiktok_pack" and any(getattr(getattr(c, "func", None), "id", "") ==
                  "chapter_video_wire_gate_errors" for c in ast.walk(n)))
    assert not any(getattr(getattr(c, "func", None), "id", "") == "chapter_video_wire_gate_errors"
                   for o in branch.orelse for c in ast.walk(o))
    assert "is_tiktok_pack = str(target).startswith(str(TIKTOK_OUTPUT_DIR.resolve()))" in ast.get_source_segment(src, gate)
    preview = ast.get_source_segment(src, fns["social_post_preview"])
    assert "allowed_roots = [campaign_root, SOCIAL_OUTPUT_DIR.resolve(), EXPERIMENT_OUTPUT_DIR.resolve()]" in preview


def test_text_release_folders_are_not_reel_folders_and_preview_refuses_reel_pack(app_env):
    app_mod, folder = app_env  # folder is a Reel pack under the (sandboxed) TIKTOK_OUTPUT_DIR
    assert not str(app_mod.OUTPUT_DIR.resolve()).startswith(str(app_mod.TIKTOK_OUTPUT_DIR.resolve()))
    with pytest.raises(RuntimeError, match="not valid"):
        app_mod.social_post_preview(str(folder), True, ["royal-road"])
