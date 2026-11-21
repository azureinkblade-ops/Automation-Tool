"""Launcher pipe-hang regression (Research repro, Nov 2026) + overall clip-step deadline.

CPU only. ComfyUI is never started: the "launchers" here are tiny Python scripts written to tmp_path.
Every spawned process is tracked through a pid file and killed in teardown.
"""
from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from tools import chapter_video_wiring as cvw


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30,
        ).stdout
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _kill(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


@pytest.fixture
def pidfiles(tmp_path):
    files: list = []
    yield files
    for f in files:
        try:
            for line in Path(f).read_text().split():
                if line.strip().isdigit():
                    _kill(int(line))
        except FileNotFoundError:
            pass


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _wait_pidfile(path: Path, seconds: float = 15.0) -> int:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if path.is_file() and path.read_text().strip().isdigit():
            return int(path.read_text().strip())
        time.sleep(0.1)
    raise AssertionError(f"pid file never written: {path}")


def test_launcher_that_leaves_child_holding_inherited_stdout_returns_fast(tmp_path, pidfiles):
    """(a) Like start_comfyui_wan.bat: spawn a long-lived child that inherits our stdout, print, exit 0.
    The old capture_output=True runner blocked on the still-open pipe; the fixed one returns in seconds."""
    child_pid = tmp_path / "child.pid"
    pidfiles.append(child_pid)
    child = _write(tmp_path, "child.py", f"""
        import os, time
        open(r"{child_pid}", "w").write(str(os.getpid()))
        time.sleep(120)
    """)
    launcher = _write(tmp_path, "launcher.py", f"""
        import subprocess, sys
        kw = {{"close_fds": False}}
        subprocess.Popen([sys.executable, r"{child}"], **kw)  # inherits this process's stdout/stderr
        print("READY: dynvram_disabled=True", flush=True)
        sys.exit(0)
    """)
    t0 = time.time()
    rc, out = cvw.default_launcher_runner([sys.executable, str(launcher)], 20.0)
    elapsed = time.time() - t0
    pid = _wait_pidfile(child_pid)
    assert rc == 0
    assert "dynvram_disabled=True" in out  # launcher output still captured (from the temp file)
    assert elapsed < 15.0, f"runner blocked {elapsed:.1f}s on the inherited handle"
    assert _pid_alive(pid)  # the long-lived child (ComfyUI stand-in) is left running, as the launcher intends


def test_hanging_launcher_times_out_kills_tree(tmp_path, pidfiles):
    """(b) A launcher that hangs itself (and has a child): TimeoutExpired within the limit, tree killed."""
    launcher_pid = tmp_path / "launcher.pid"
    child_pid = tmp_path / "child.pid"
    pidfiles.extend([launcher_pid, child_pid])
    child = _write(tmp_path, "child.py", f"""
        import os, time
        open(r"{child_pid}", "w").write(str(os.getpid()))
        time.sleep(120)
    """)
    launcher = _write(tmp_path, "launcher.py", f"""
        import os, subprocess, sys, time
        open(r"{launcher_pid}", "w").write(str(os.getpid()))
        subprocess.Popen([sys.executable, r"{child}"])
        time.sleep(120)
    """)
    t0 = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        cvw.default_launcher_runner([sys.executable, str(launcher)], 4.0)
    assert time.time() - t0 < 45.0
    lp = _wait_pidfile(launcher_pid, 1.0)
    cp = _wait_pidfile(child_pid, 5.0)
    deadline = time.time() + 10
    while time.time() < deadline and (_pid_alive(lp) or _pid_alive(cp)):
        time.sleep(0.2)
    assert not _pid_alive(lp)
    assert not _pid_alive(cp)


def test_hanging_launcher_start_ends_in_media_hold(tmp_path, monkeypatch):
    """(b) end to end: the start call times out -> ComfyReady not ok -> produce_chapter_clip MEDIA_HOLD."""
    from PIL import Image

    still = tmp_path / "still.png"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(still)
    calls = []

    def runner(args, timeout):
        calls.append(list(args))
        if args[1:] == ["-Status"]:
            return 0, "STATUS port8188_busy=False our_pid=none\nSTATUS /system_stats unreachable"
        if len(args) == 1:  # the start call
            raise subprocess.TimeoutExpired(args, timeout)
        return 1, "STOP: nothing"

    cfg = cvw.ChapterVideoConfig.from_env({})
    res = cvw.produce_chapter_clip(
        still, workflow_id="wf-hang", store_root=tmp_path / "store", still_approved=True, cfg=cfg,
        comfy_runner=runner, pipeline_builder=lambda b: pytest.fail("no pipeline when ComfyUI is not ready"),
        step_timeout_s=60,
    )
    assert res.outcome == cvw.MEDIA_HOLD
    assert "COMFY_START_ERROR:TimeoutExpired" in (res.hold_reason or "")
    assert res.asset_path is None


def test_overall_clip_step_timeout_ends_in_media_hold(tmp_path):
    """Product Performance: one overall deadline on the clip step -> MEDIA_HOLD, never a hang."""
    import threading
    from PIL import Image

    still = tmp_path / "still.png"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(still)
    release = threading.Event()
    stops = []

    def runner(args, timeout):
        if args[1:] == ["-Stop"]:
            stops.append(1)
            release.set()  # stopping ComfyUI is what unblocks a stuck worker in production
            return 0, "STOP: ok"
        if args[1:] == ["-Status"]:
            return 0, "STATUS port8188_busy=True\nSTATUS dynvram_disabled=True"
        return 0, ""

    class StuckPipeline:
        def produce_social_media(self, *a, **k):
            release.wait(30)
            raise RuntimeError("comfy gone")

    cfg = dataclasses.replace(cvw.ChapterVideoConfig.from_env({}), idle_restart=False)  # reuse running instance
    t0 = time.time()
    res = cvw.produce_chapter_clip(
        still, workflow_id="wf-deadline", store_root=tmp_path / "store", still_approved=True, cfg=cfg,
        comfy_runner=runner, pipeline_builder=lambda b: StuckPipeline(), step_timeout_s=1.5,
    )
    assert time.time() - t0 < 10
    assert res.outcome == cvw.MEDIA_HOLD
    assert "CLIP_STEP_TIMEOUT" in (res.hold_reason or "")
    assert not stops  # a ComfyUI this run did NOT start is never stopped by the deadline
    release.set()


def test_step_timeout_env_default_and_parse():
    assert cvw.ChapterVideoConfig.from_env({}).step_timeout_s == cvw.DEFAULT_STEP_TIMEOUT_S
    assert cvw.ChapterVideoConfig.from_env({cvw.ENV_STEP_TIMEOUT: "900"}).step_timeout_s == 900.0
    assert cvw.ChapterVideoConfig.from_env({cvw.ENV_STEP_TIMEOUT: "5"}).step_timeout_s == 60.0  # floor
    bad = cvw.ChapterVideoConfig.from_env({cvw.ENV_STEP_TIMEOUT: "soon"})
    assert any(cvw.ENV_STEP_TIMEOUT in p for p in bad.problems)


def test_no_capture_output_on_launcher_path():
    import inspect

    import ast
    import textwrap as tw

    fn = ast.parse(tw.dedent(inspect.getsource(cvw.default_launcher_runner))).body[0]
    body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) else fn.body  # code only, not the docstring
    src = "\n".join(ast.unparse(n) for n in body)
    assert "capture_output" not in src
    assert "PIPE" not in src
    assert "shell=True" not in src
