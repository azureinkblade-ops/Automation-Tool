"""Opt-in, non-model Windows pipe qualification for Kilo output capture."""

from __future__ import annotations

import os
import sys

import pytest

from tools.hermes_core import kilo_adapter


@pytest.mark.skipif(
    os.environ.get("EA4E_RUN_INERT_KILO_CAPTURE") != "1",
    reason="requires explicit non-model process qualification",
)
def test_inert_python_capture_limits_on_host(monkeypatch, tmp_path):
    monkeypatch.setattr(kilo_adapter, "KILO_CWD", tmp_path)
    controller = kilo_adapter.KiloProcessController({})
    base = [sys.executable, "-B", "-c"]

    normal = controller.execute(base + ["print('CAPTURE_OK')"], timeout=5)
    assert normal.returncode == 0
    assert normal.stdout.strip() == "CAPTURE_OK"
    assert normal.output_overflowed is False

    large = controller.execute(
        base + ["import sys; sys.stdout.buffer.write(b'x'*(4*1024*1024+1)); sys.stdout.flush()"],
        timeout=10,
    )
    assert large.returncode == -1
    assert large.output_overflowed is True
    assert len(large.stdout) == kilo_adapter.MAX_STDOUT_BYTES

    noisy_error = controller.execute(
        base + ["import sys; sys.stderr.buffer.write(b'e'*(128*1024+1)); sys.stderr.flush()"],
        timeout=5,
    )
    assert noisy_error.returncode == -1
    assert noisy_error.output_overflowed is True
    assert len(noisy_error.stderr) == kilo_adapter.MAX_STDERR_BYTES

    slow = controller.execute(base + ["import time; time.sleep(10)"], timeout=1)
    assert slow.returncode == -1
    assert slow.timed_out is True
