"""Two deterministic non-model probes under a dedicated process envelope."""

import json
import os
import sqlite3
import subprocess

import pytest

from tools import ea4e67y_worker_admission as admission
from tools.ea4e69_worker_launcher import BoundedWorkerLauncher


def spawn(tmp_path, base, worker_node):
    environment = {name: os.environ[name] for name in ("SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP") if name in os.environ}
    launcher = BoundedWorkerLauncher(subprocess.Popen)
    registry = tmp_path / "registry.sqlite3"
    argv = [str(admission.PYTHON), str(admission.HELPER), *admission.FLAGS[worker_node], str(registry)]
    child = launcher.spawn(worker_node, argv, admission.ROOT, environment, base)
    return launcher, child, registry


def request():
    return json.dumps({"protocol_version": "hermes-local-worker-v1", "idempotency_key": "ea4e70-probe", "launch_attempt_id": "ea4e70-launch"}) + "\n"


def test_guarded_worker_accepts(tmp_path, tmp_path_factory):
    node = admission.WORKER + "RealSpawnTests::test_valid_probe_returns_started"
    launcher, child, registry = spawn(tmp_path, tmp_path_factory.getbasetemp(), node)
    try:
        stdout, stderr = child.communicate(request(), timeout=5)
        assert child.returncode == 0, stderr
        ack = json.loads(stdout)
        assert ack["state"] == "STARTED"
        assert ack["idempotency_key"] == "ea4e70-probe"
        conn = sqlite3.connect(registry)
        try:
            assert conn.execute("SELECT state FROM local_worker_idempotency").fetchall() == [("STARTED",)]
        finally:
            conn.close()
    finally:
        launcher.cleanup()
    assert child.poll() is not None
    assert all(pipe.closed for pipe in (child.stdin, child.stdout, child.stderr))


def test_timeout_reaps_owned_child(tmp_path, tmp_path_factory):
    node = admission.WORKER + "TimeoutMechanicsTests::test_ack_timeout_terminates_only_owned_child"
    launcher, child, registry = spawn(tmp_path, tmp_path_factory.getbasetemp(), node)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            child.communicate(request(), timeout=0.5)
    finally:
        launcher.cleanup(timeout=1)
    assert child.poll() is not None
    assert all(pipe.closed for pipe in (child.stdin, child.stdout, child.stderr))
