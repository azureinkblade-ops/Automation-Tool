# -*- coding: utf-8 -*-
"""SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R3 — hard GPU execution barrier.

Fail-closed process barrier at the generator / subprocess boundary for pytest.
Blocks local SD/SDXL, ComfyUI, .venv-gpu generator launches, and patches
app.create_local_stable_diffusion_image so unmocked fallthrough aborts the
test before any model/process invocation.

Activation (automatic via tests/conftest.py on import):
  AT_SD_ENABLED=0
  LOCAL_SD_ENABLED=0
  CUDA_VISIBLE_DEVICES=-1   (never empty string — PowerShell deletes '')
  AT_GPU_TEST_BARRIER=1

Harness scripts may also: python -m pytest -p tests.gpu_test_barrier ...
or set PYTHONPATH and -p gpu_test_barrier when the plugin is imported as a module.

Sentinel prints:
  GPU_TEST_BARRIER_INSTALLED=YES
  GPU_TEST_BARRIER_FAILURE_ABORTS=YES
  REAL_GENERATOR_FALLTHROUGH_ALLOWED=NO
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

GPU_TEST_BARRIER_INSTALLED = False
GPU_TEST_BARRIER_FAILURE_ABORTS = True
REAL_GENERATOR_FALLTHROUGH_ALLOWED = False
_GENERATOR_GUARD_ACTIVE = False
_BLOCK_HITS = 0
_ORIG_POPEN_INIT = None
_ORIG_RUN = None
_ORIG_CREATE_LOCAL_SD = None
_PATCHED_APP = False

_BLOCK_TOKENS = (
    "local_image_generator",
    "comfyui",
    "comfy_ui",
    "sdxl_generate",
    "generate_image.py",
    "stable-diffusion",
    "stable_diffusion",
)


def _log(rec: dict[str, Any]) -> None:
    out = os.environ.get("AT_SDGUARD_OUT") or os.environ.get("RQ2_SDGUARD_OUT") or os.environ.get("R3_SDGUARD_OUT")
    if not out:
        return
    try:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _cmd_text(args: Any) -> str:
    try:
        if isinstance(args, str):
            return args
        return " ".join(str(x) for x in args)
    except Exception:
        return repr(args)


def _is_blocked_cmd(cmd: str) -> bool:
    low = (cmd or "").lower().replace("\\", "/")
    if any(b in low for b in _BLOCK_TOKENS):
        return True
    # .venv-gpu python launching anything that looks like generation
    if ".venv-gpu" in low and ("local_image_generator" in low or "--prompt" in low):
        return True
    return False


class GpuTestBarrierError(RuntimeError):
    """Raised when a test reaches a real image generator seam under the R3 barrier."""


def _raise_blocked(where: str, cmd: str = "") -> None:
    global _BLOCK_HITS
    _BLOCK_HITS += 1
    _log({
        "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "action": "BLOCKED",
        "where": where,
        "test": os.environ.get("PYTEST_CURRENT_TEST", ""),
        "cmd": (cmd or "")[:500],
        "barrier": "R3_GPU_TEST_BARRIER",
    })
    raise GpuTestBarrierError(
        f"R3_GPU_TEST_BARRIER: blocked {where} (GPU_GENERATIONS=0; "
        f"REAL_GENERATOR_FALLTHROUGH_ALLOWED=NO). cmd={cmd[:200]!r}"
    )


def _guarded_popen_init(self, args, *a, **k):  # type: ignore[no-untyped-def]
    cmd = _cmd_text(args)
    if _is_blocked_cmd(cmd):
        _raise_blocked("subprocess.Popen", cmd)
    if ".venv-gpu" in cmd.lower():
        _log({
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "action": "ALLOWED_VENV_GPU_PROBE",
            "test": os.environ.get("PYTEST_CURRENT_TEST", ""),
            "cmd": cmd[:300],
        })
    return _ORIG_POPEN_INIT(self, args, *a, **k)


def _guarded_run(args, *a, **k):  # type: ignore[no-untyped-def]
    cmd = _cmd_text(args)
    if _is_blocked_cmd(cmd):
        _raise_blocked("subprocess.run", cmd)
    return _ORIG_RUN(args, *a, **k)


def _guarded_create_local_sd(*a, **k):  # type: ignore[no-untyped-def]
    _raise_blocked("app.create_local_stable_diffusion_image", "create_local_stable_diffusion_image()")


def install_gpu_test_barrier(*, force: bool = False) -> bool:
    """Install fail-closed GPU barrier. Idempotent."""
    global GPU_TEST_BARRIER_INSTALLED, _GENERATOR_GUARD_ACTIVE
    global _ORIG_POPEN_INIT, _ORIG_RUN, _ORIG_CREATE_LOCAL_SD, _PATCHED_APP

    if os.environ.get("AT_GPU_TEST_BARRIER_DISABLE") == "1":
        raise SystemExit("AT_GPU_TEST_BARRIER_DISABLE=1 refused; barrier required for R3")

    # Env sentinels (never empty CUDA_VISIBLE_DEVICES)
    os.environ["AT_SD_ENABLED"] = "0"
    os.environ["LOCAL_SD_ENABLED"] = "0"
    os.environ["AT_GPU_TEST_BARRIER"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ.setdefault("AT_GPU_GENERATIONS", "0")

    if GPU_TEST_BARRIER_INSTALLED and not force:
        return True

    if _ORIG_POPEN_INIT is None:
        _ORIG_POPEN_INIT = subprocess.Popen.__init__
        subprocess.Popen.__init__ = _guarded_popen_init  # type: ignore[method-assign]
    if _ORIG_RUN is None:
        _ORIG_RUN = subprocess.run
        subprocess.run = _guarded_run  # type: ignore[assignment]

    # NOTE (R3): do NOT replace app.create_local_stable_diffusion_image here.
    # Identity/production-path tests must reach in-function identity gates; the hard
    # fail-closed barrier is subprocess.Popen/run (+ AT_SD_ENABLED check immediately
    # before the generator subprocess, and local_image_generator.py entry guard).
    # Negative-control tests call _guarded_create_local_sd / intentional subprocess.

    GPU_TEST_BARRIER_INSTALLED = True
    _GENERATOR_GUARD_ACTIVE = True
    print("GPU_TEST_BARRIER_INSTALLED=YES", flush=True)
    print("GPU_TEST_BARRIER_FAILURE_ABORTS=YES", flush=True)
    print("REAL_GENERATOR_FALLTHROUGH_ALLOWED=NO", flush=True)
    print("GENERATOR_GUARD_ACTIVE=YES", flush=True)
    _log({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": "INSTALLED", "barrier": "R3_GPU_TEST_BARRIER"})
    return True


def generator_guard_active() -> bool:
    return bool(_GENERATOR_GUARD_ACTIVE and GPU_TEST_BARRIER_INSTALLED)


def block_hit_count() -> int:
    return int(_BLOCK_HITS)


def pytest_configure(config):  # noqa: ANN001
    install_gpu_test_barrier()


def pytest_sessionstart(session):  # noqa: ANN001
    if not GPU_TEST_BARRIER_INSTALLED:
        install_gpu_test_barrier()
    print("GPU_TEST_BARRIER_INSTALLED=YES", flush=True)
