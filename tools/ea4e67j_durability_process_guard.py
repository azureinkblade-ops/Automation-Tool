"""Bounded Python-helper qualification; not a universal OS sandbox."""

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tests/hermes_core/fixtures/durable_auth_process_helper.py"
PYTHON = Path(r"C:\Users\David\Documents\Automation tool\.venv-stage2-v2\Scripts\python.exe")
HELPER_SHA256 = "d2aa771a24adacd7fb3f3b1c2c8b3eaa6b8800dfff27315fd7010d02d7265ab1"
PYTHON_SHA256 = "0a864203aee170314ece97beaad6e50e226e76f0a3d73380a93ec472ed74f040"
PROCESS_BUDGET = 14
NODES = {
    "tests/hermes_core/test_ea4e33_operational_safety.py::test_multi_process_claim_tested",
    "tests/hermes_core/test_ea4e33_operational_safety.py::test_os_process_precommit_crash_tested",
    "tests/hermes_core/test_ea4e33_operational_safety.py::test_os_process_postcommit_crash_tested",
    "tests/hermes_core/test_ea4e33a_store_rollback_detection.py::test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent",
    "tests/hermes_core/test_ea4e67k_process_durability.py::test_abrupt_postcommit_crash_keeps_consumption_and_fails_closed",
    "tests/hermes_core/test_ea4e67k_process_durability.py::test_simultaneous_claims_have_one_winner_and_three_clean_denials",
}
_originals = []
_children = []
_denials = []


def pytest_configure(config):
    if set(config.args) != NODES or len(config.args) != len(NODES):
        raise pytest.UsageError("durability qualification requires exactly six frozen test nodes")
    if Path(sys.executable).resolve() != PYTHON.resolve() or hashlib.sha256(PYTHON.read_bytes()).hexdigest() != PYTHON_SHA256:
        raise pytest.UsageError("frozen interpreter identity mismatch")
    if hashlib.sha256(HELPER.read_bytes()).hexdigest() != HELPER_SHA256:
        raise pytest.UsageError("frozen helper identity mismatch")
    if not config.option.basetemp:
        raise pytest.UsageError("explicit isolated basetemp required")
    base = Path(config.option.basetemp).resolve()
    if not base.is_relative_to(ROOT) or base == ROOT or base.exists():
        raise pytest.UsageError("use a fresh isolated basetemp inside this worktree")
    base.mkdir(parents=True)
    # pytest owns basetemp; helper files live in a separate temporary root.
    temporary = base.with_name(base.name + "-helpers")
    temporary.mkdir()
    import tempfile
    _originals.append((tempfile, "tempdir", tempfile.tempdir))
    tempfile.tempdir = str(temporary)
    real_popen = subprocess.Popen

    def deny(message):
        _denials.append(message)
        raise RuntimeError(message)

    def launch(argv, **kwargs):
        if not isinstance(argv, list) or len(argv) not in (4, 7):
            return deny("unexpected helper argv")
        if Path(argv[0]).resolve() != Path(sys.executable).resolve() or Path(argv[1]).resolve() != HELPER:
            return deny("unqualified executable or helper")
        if hashlib.sha256(HELPER.read_bytes()).hexdigest() != HELPER_SHA256 or hashlib.sha256(PYTHON.read_bytes()).hexdigest() != PYTHON_SHA256:
            return deny("qualification identity changed")
        if not ((len(argv) == 4 and argv[2] == "precommit-crash") or (len(argv) == 7 and argv[2] in {"claim", "postcommit-crash"})):
            return deny("unexpected helper mode")
        for value in argv[3:5] if len(argv) == 7 else argv[3:4]:
            path = Path(value).resolve()
            if not any(path.is_relative_to(root) for root in (base, temporary)):
                return deny("helper state outside isolated roots")
        if len(argv) == 7 and not isinstance(json.loads(argv[5]), dict):
            return deny("invalid claim payload")
        if (set(kwargs) != {"stdout", "stderr", "text"}
                or kwargs["stdout"] != subprocess.PIPE
                or kwargs["stderr"] != subprocess.PIPE or kwargs["text"] is not True
                or len(_children) >= PROCESS_BUDGET):
            return deny("unexpected launch options or exhausted process budget")
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
        environment.update(TEMP=str(temporary), TMP=str(temporary), PYTHONNOUSERSITE="1")
        child = real_popen(argv, stdin=subprocess.DEVNULL, env=environment, cwd=ROOT, **kwargs)
        _children.append(child)
        return child

    for owner, name, replacement in (
        (subprocess, "Popen", launch),
        (os, "system", lambda *a, **k: deny("shell prohibited")),
        (socket.socket, "connect", lambda *a, **k: deny("network prohibited")),
        (socket.socket, "connect_ex", lambda *a, **k: deny("network prohibited")),
    ):
        _originals.append((owner, name, getattr(owner, name)))
        setattr(owner, name, replacement)


def pytest_sessionfinish(session, exitstatus):
    for child in _children:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
            _denials.append("unfinished helper killed")
    if _denials:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"EA4E67J_HELPER_LAUNCHES={len(_children)} DENIALS={len(_denials)}")


def pytest_unconfigure(config):
    for owner, name, original in reversed(_originals):
        setattr(owner, name, original)
    _originals.clear()
