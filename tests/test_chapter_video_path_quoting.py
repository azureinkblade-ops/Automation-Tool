"""Path quoting for the chapter video path: every subprocess gets an argv LIST, so a repo/work path with
spaces (``...\\Documents\\Automation tool``) can never be split into stray arguments. CPU only; no ComfyUI.
"""
from __future__ import annotations

import ast
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_chapter_video_wiring import BUSY_OK, FFMPEG, FFPROBE, FakeComfy, Launcher, _still, needs_ffmpeg
from tools import chapter_video_wiring as cvw

REPO = Path(__file__).resolve().parents[1]
SPACED = "Automation tool"  # the real repo folder name: contains a space
VIDEO_PATH_MODULES = [
    "tools/chapter_video_wiring.py",
    "tools/comfy_http_i2v_transport.py",
    "tools/i2v_presentation_adapter.py",
    "tools/media_validity.py",
    "tools/i2v_production_adapter.py",
    "tools/media_pipeline_i2v_wiring.py",
    "tools/media_pipeline_integration.py",
    "tools/i2v_backend_registry.py",
]
SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}


def _subprocess_calls(path):
    tree = ast.parse((REPO / path).read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "subprocess" and f.attr in SUBPROCESS_FUNCS:
                yield node
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "os" and f.attr in {"system", "popen"}:
                yield node


@pytest.mark.parametrize("rel", VIDEO_PATH_MODULES)
def test_video_path_modules_never_use_shell_or_string_commands(rel):
    for call in _subprocess_calls(rel):
        for kw in call.keywords:
            assert not (kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False)), f"{rel}:{call.lineno} shell="
        if isinstance(call.func, ast.Attribute) and call.func.attr in SUBPROCESS_FUNCS:
            arg0 = call.args[0] if call.args else None
            assert isinstance(arg0, (ast.List, ast.Name, ast.Call)), f"{rel}:{call.lineno} command must be a list/variable, not a string"
            assert not isinstance(arg0, (ast.Constant, ast.JoinedStr, ast.BinOp)), f"{rel}:{call.lineno} string command"
        assert not (isinstance(call.func, ast.Attribute) and call.func.value.id == "os"), f"{rel}:{call.lineno} os.system/popen"


def test_app_video_path_subprocesses_are_argv_lists_without_shell():
    """app.py's ffmpeg/ffprobe builders on the video path (and the chapter wiring call sites) are lists, no shell=True."""
    src = (REPO / "app.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(src)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "subprocess" and node.func.attr in SUBPROCESS_FUNCS:
            if any(kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False) for kw in node.keywords):
                bad.append(node.lineno)
            if node.args and isinstance(node.args[0], (ast.Constant, ast.JoinedStr, ast.BinOp)):
                bad.append(node.lineno)
    assert bad == []
    assert "os.system(" not in src and "os.popen(" not in src


def test_launcher_argv_keeps_a_spaced_path_as_one_element():
    bat = rf"C:\Users\David\ComfyUI Launch\{SPACED}\start_comfyui_wan.bat"
    assert cvw.launcher_argv(bat, "-Status") == [bat, "-Status"]
    assert cvw.launcher_argv(bat) == [bat]


def test_loop_ffmpeg_argv_keeps_spaced_paths_whole():
    argv = cvw.build_loop_ffmpeg_argv(rf"C:\ff mpeg\ffmpeg.exe", rf"C:\x\{SPACED}\in clip.mp4", rf"C:\x\{SPACED}\out clip.mp4", 2, "scale=1:1")
    assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
    assert rf"C:\x\{SPACED}\in clip.mp4" in argv and rf"C:\x\{SPACED}\out clip.mp4" in argv and argv[0] == rf"C:\ff mpeg\ffmpeg.exe"
    assert argv[argv.index("-stream_loop") + 1] == "2"


def test_ensure_comfy_ready_calls_runner_with_argv_lists(tmp_path):
    seen = []

    def runner(argv, timeout):
        seen.append(argv)
        assert isinstance(argv, list)
        return 0, BUSY_OK

    cfg = dataclasses.replace(cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_COMFY_LAUNCHER": rf"C:\a b\{SPACED}\start_comfyui_wan.bat"}),
                              idle_restart=False)
    assert cvw.ensure_comfy_ready(cfg, runner).ok
    assert seen == [[rf"C:\a b\{SPACED}\start_comfyui_wan.bat", "-Status"]]


@pytest.mark.skipif(os.name != "nt", reason="the launcher is a Windows .bat")
def test_real_subprocess_runs_a_bat_in_a_spaced_path_with_its_flags_intact(tmp_path):
    """An echo-only stub .bat (same shape as the launcher: %* forwarding, %~dp0) in a folder with a space and
    parentheses, run through the real default_launcher_runner. It starts nothing; no ComfyUI is involved."""
    d = tmp_path / f"{SPACED} (v2)"
    d.mkdir()
    bat = d / "stub_launcher.bat"
    bat.write_text(
        "@echo off\r\n"
        "echo ARGS=[%*]\r\n"
        "echo DP0=%~dp0\r\n"
        "if /I \"%~1\"==\"-Status\" (echo STATUS port8188_busy=True our_pid=1& echo STATUS dynvram_disabled=True)\r\n"
        "exit /b 0\r\n",
        encoding="ascii",
    )
    rc, out = cvw.default_launcher_runner(cvw.launcher_argv(str(bat), "-Status"), 60.0)
    assert rc == 0 and "ARGS=[-Status]" in out and str(d) in out
    st = cvw.parse_launcher_status(out)
    assert st.port_busy is True and st.dynvram_disabled is True
    cfg = dataclasses.replace(cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_COMFY_LAUNCHER": str(bat)}), idle_restart=False)
    ready = cvw.ensure_comfy_ready(cfg)  # real runner, real .bat in a spaced path
    assert ready.ok and ready.reason == "reused_running_comfyui"


@pytest.mark.skipif(os.name != "nt", reason="the launcher is a Windows .bat")
def test_real_subprocess_bat_stop_and_start_flags_reach_the_bat_in_a_spaced_path(tmp_path):
    d = tmp_path / SPACED
    d.mkdir()
    bat = d / "stub_launcher.bat"
    bat.write_text("@echo off\r\necho ARGS=[%*]\r\nexit /b 0\r\n", encoding="ascii")
    assert "ARGS=[-Stop]" in cvw.default_launcher_runner(cvw.launcher_argv(str(bat), "-Stop"), 60.0)[1]
    assert "ARGS=[]" in cvw.default_launcher_runner(cvw.launcher_argv(str(bat)), 60.0)[1]


@needs_ffmpeg
def test_real_ffmpeg_ffprobe_stack_works_inside_a_spaced_repo_path(tmp_path, monkeypatch):
    """Wan 73-frame path through the REAL presentation ffmpeg + ffprobe gate with the whole work tree in a spaced dir,
    recording every subprocess call to prove argv lists (no shell) carry the spaced paths as single elements."""
    work = tmp_path / SPACED
    work.mkdir()
    calls = []
    real_run = subprocess.run

    def spy(cmd, *a, **kw):
        calls.append((cmd, kw))
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", spy)
    cfg = dataclasses.replace(cvw.ChapterVideoConfig.from_env({}), idle_restart=False)
    transport = FakeComfy(work)
    res = cvw.produce_chapter_clip(
        _still(work), workflow_id="chapter-clip:spaces", store_root=work / "store", still_approved=True, cfg=cfg,
        pipeline_builder=lambda b: cvw.build_backend_pipeline(cfg, b, work / "store", transport=transport),
        comfy_runner=Launcher([BUSY_OK]))
    assert res.ready, res.hold_reason
    assert SPACED in res.asset_path and res.frame_count == 73 and res.duration_seconds >= 3.0
    media_calls = [(c, kw) for c, kw in calls if isinstance(c, list) and c and Path(str(c[0])).stem.lower() in {"ffmpeg", "ffprobe"}]
    spaced_hits = [c for c, kw in media_calls if any(SPACED in str(a) for a in c)]
    assert spaced_hits, "expected ffmpeg/ffprobe calls that carry the spaced path"
    for cmd, kw in media_calls:
        assert not kw.get("shell")
        for a in cmd:
            assert isinstance(a, str)
            if SPACED in a:
                assert a.count(SPACED) == 1 and (a.lower().endswith((".mp4", ".png")) or a.endswith(SPACED))  # whole path, one element


@needs_ffmpeg
def test_real_loop_fallback_inside_a_spaced_repo_path(tmp_path):
    work = tmp_path / f"{SPACED} (loop)"
    work.mkdir()
    cfg = dataclasses.replace(
        cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_FRAMES": "17", "CHAPTER_VIDEO_LOOP_FALLBACK": "1"}), idle_restart=False)
    transport = FakeComfy(work)
    res = cvw.produce_chapter_clip(
        _still(work), workflow_id="chapter-clip:loop-spaces", store_root=work / "store", still_approved=True, cfg=cfg,
        pipeline_builder=lambda b: cvw.build_backend_pipeline(cfg, b, work / "store", transport=transport,
                                                               render=cvw.LoopingRender(cfg.min_seconds)),
        comfy_runner=Launcher([BUSY_OK]))
    assert res.ready, res.hold_reason
    assert res.duration_seconds >= 3.0 and SPACED in res.asset_path  # 17 frames (0.7 s) only reaches 3 s via the loop
