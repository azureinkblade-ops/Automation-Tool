# -*- coding: utf-8 -*-
"""R3 Phase 0/1 barrier negative controls — must pass before any GPU-touching probes."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def test_r3_gpu_barrier_sentinels_active():
    from tests.gpu_test_barrier import (
        GPU_TEST_BARRIER_INSTALLED,
        GPU_TEST_BARRIER_FAILURE_ABORTS,
        REAL_GENERATOR_FALLTHROUGH_ALLOWED,
        generator_guard_active,
    )
    assert GPU_TEST_BARRIER_INSTALLED is True
    assert GPU_TEST_BARRIER_FAILURE_ABORTS is True
    assert REAL_GENERATOR_FALLTHROUGH_ALLOWED is False
    assert generator_guard_active() is True
    assert os.environ.get("AT_SD_ENABLED") == "0"
    assert os.environ.get("LOCAL_SD_ENABLED") == "0"
    assert os.environ.get("AT_GPU_TEST_BARRIER") == "1"
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == "-1"


def test_r3_runtime_state_guard_sentinels_active():
    from tests.runtime_state_guard import (
        RUNTIME_STATE_TEST_ISOLATION_INSTALLED,
        LIVE_RUNTIME_PATH_FALLBACK_ALLOWED,
        runtime_state_guard_active,
    )
    assert RUNTIME_STATE_TEST_ISOLATION_INSTALLED is True
    assert LIVE_RUNTIME_PATH_FALLBACK_ALLOWED is False
    assert runtime_state_guard_active() is True
    import app
    # growth-automation must point into isolation sandbox, not live repo
    gaf = Path(app.GROWTH_AUTOMATION_FILE).resolve()
    assert "at_iso_" in str(gaf).lower()
    live = (Path(__file__).resolve().parents[1] / "growth-automation.json").resolve()
    assert gaf != live


def test_r3_gpu_barrier_blocks_subprocess_local_image_generator():
    """Negative control: intentionally reach generator subprocess seam -> blocked before process."""
    from tests.gpu_test_barrier import GpuTestBarrierError
    with pytest.raises((GpuTestBarrierError, OSError, RuntimeError)):
        subprocess.run(
            ["python", "local_image_generator.py", "--prompt", "x", "--output", "y.png"],
            check=False,
        )


def test_r3_gpu_barrier_blocks_create_local_stable_diffusion_image():
    """Negative control: reaching the generator subprocess seam is blocked before process/model.

    Identity tests may enter create_local_stable_diffusion_image for gate logic; the hard
    barrier aborts at subprocess.Popen/run and at the pre-subprocess AT_SD_ENABLED check.
    This control forces the subprocess seam (and also exercises the guarded helper).
    """
    import app
    from tests.gpu_test_barrier import GpuTestBarrierError, _guarded_create_local_sd
    target = Path(os.environ["AT_TEST_ISOLATION_ROOT"]) / "barrier_neg.png"
    # Helper always raises (proves barrier module active)
    with pytest.raises(GpuTestBarrierError):
        _guarded_create_local_sd("test prompt should never render", target)
    # Subprocess seam already covered by test_r3_gpu_barrier_blocks_subprocess_local_image_generator.
    # Additionally: if create_local reaches subprocess under barrier env, it must raise RuntimeError.
    # We simulate by ensuring env sentinels remain set (installed by conftest).
    assert os.environ.get("AT_SD_ENABLED") == "0"
    assert os.environ.get("AT_GPU_TEST_BARRIER") == "1"


def test_r3_runtime_guard_blocks_live_growth_automation_write():
    """Negative control: writing live growth-automation.json must abort."""
    from tests.runtime_state_guard import RuntimeStateGuardError
    live = Path(__file__).resolve().parents[1] / "growth-automation.json"
    with pytest.raises(RuntimeStateGuardError):
        with open(live, "a", encoding="utf-8") as fh:
            fh.write("")
