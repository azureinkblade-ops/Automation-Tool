"""Inert tests for the one-shot Kilo host launcher; never starts Kilo."""

import json
import os
from pathlib import Path
import sys

import pytest

from tools.ea4e92ck_kilo_inert_probe import MARKER
from tools.ea4e92cm_kilo_inert_runner import (
    ProbeRefused, _exact_text_marker, bounded_child, run_once, validate_plan,
)


PLAN = Path(r"C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo-inert-probe-92ck-20261004\launch-plan.json")
SHAPE_PLAN = Path(r"C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo-shape-probe-92cr-20261004\launch-plan.json")


def test_prepared_plan_is_dummy_only():
    if not PLAN.exists():
        pytest.skip("host probe has not been prepared")
    if (PLAN.parent / "attempt.json").exists():
        pytest.skip("one-shot host probe has already been consumed")
    plan = validate_plan(PLAN)
    assert plan["credential_class"] == "DUMMY_LOCAL_ONLY"
    assert plan["real_provider_calls_authorized"] is False


def test_fresh_shape_plan_validates_without_launch():
    if not SHAPE_PLAN.exists():
        pytest.skip("fresh shape probe has not been prepared")
    if (SHAPE_PLAN.parent / "attempt.json").exists():
        pytest.skip("fresh shape probe has already been consumed")
    plan = validate_plan(SHAPE_PLAN)
    assert plan["credential_class"] == "DUMMY_LOCAL_ONLY"
    assert plan["launch_authorized"] is False
    assert plan["network_isolation_verified"] is False
    assert not (SHAPE_PLAN.parent / "attempt.json").exists()


def test_fresh_shape_launch_claims_before_injected_child(monkeypatch, tmp_path):
    import tools.ea4e92cm_kilo_inert_runner as runner

    class FakeServer:
        events = []

        def __init__(self, address):
            assert address == ("127.0.0.1", runner.SHAPE_PROBE_PORT)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def serve_forever(self):
            pass

        def shutdown(self):
            pass

    plan = tmp_path / "launch-plan.json"
    plan.write_text("{}", encoding="ascii")
    monkeypatch.setattr(runner, "SHAPE_PROBE_ROOT", tmp_path)
    monkeypatch.setattr(runner, "validate_plan", lambda _path: {
        "cwd": str(tmp_path), "argv": ["injected-only"], "env": {},
    })
    monkeypatch.setattr(runner, "RecordingServer", FakeServer)
    calls = []

    def fake_child(argv, *, cwd, env, timeout):
        assert (tmp_path / "attempt.json").exists()
        assert timeout == runner.TIMEOUT_SECONDS
        calls.append((argv, cwd, env))
        return {"pid": 1, "returncode": 0, "timed_out": False,
                "output_overflowed": False, "capture_errors": [],
                "elapsed_seconds": 0, "stdout": b"", "stderr": b""}

    monkeypatch.setattr(runner, "bounded_child", fake_child)
    result = run_once(plan)
    assert result == tmp_path / "probe-result.json"
    assert len(calls) == 1
    assert json.loads(result.read_text(encoding="ascii"))["automatic_retry"] is False


def test_plan_rejects_other_root(tmp_path):
    plan = tmp_path / "launch-plan.json"
    plan.write_text("{}", encoding="ascii")
    with pytest.raises(ProbeRefused, match="unexpected probe root"):
        validate_plan(plan)


def test_exact_marker_requires_json_text_part():
    valid = json.dumps({"type": "text", "part": {"text": MARKER}}).encode()
    assert _exact_text_marker(valid)
    assert not _exact_text_marker(MARKER.encode())
    assert not _exact_text_marker(json.dumps({"type": "text", "part": {"text": MARKER + "!"}}).encode())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job object")
def test_bounded_child_uses_inert_python_process(tmp_path):
    result = bounded_child(
        [sys.executable, "-c", "print('inert local child')"],
        cwd=str(tmp_path), env=dict(os.environ), timeout=5,
    )
    assert result["returncode"] == 0
    assert result["stdout"].strip() == b"inert local child"
    assert not result["timed_out"]
    assert not result["output_overflowed"]
    assert not result["capture_errors"]
