"""Fake-only missing-executable qualification; no constructor call."""

import os
import subprocess
import sys

import pytest

from tools import ea4e73_worker_matrix_guard as guard


def options(tmp_path):
    environment = {name: os.environ[name] for name in ("SYSTEMROOT", "SYSTEMDRIVE") if name in os.environ}
    environment.update(TEMP=str(tmp_path), TMP=str(tmp_path))
    return dict(cwd=guard.admission.ROOT, env=environment, shell=False, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)


def test_exact_sync_missing_case_admitted(tmp_path):
    guard.missing_executable_case(guard.SYNC, ["C:/does/not/exist/python.exe", str(guard.admission.HELPER)], options(tmp_path), tmp_path, {})


@pytest.mark.parametrize("change", ["node", "budget", "executable", "helper", "length", "environment", "flags"])
def test_nonlaunch_identity_cannot_grant_other_authority(tmp_path, change):
    node, counts = guard.SYNC, {}
    command = ["C:/does/not/exist/python.exe", str(guard.admission.HELPER)]
    opts = options(tmp_path)
    if change == "node":
        node = "other"
    elif change == "budget":
        counts[node] = 1
    elif change == "executable":
        command[0] = str(guard.admission.PYTHON)
    elif change == "helper":
        command[1] = "other"
    elif change == "length":
        command.append("other")
    elif change == "environment":
        opts["env"]["API_KEY"] = "not-a-secret"
    else:
        opts["creationflags"] = -1
    with pytest.raises(ValueError):
        guard.missing_executable_case(node, command, opts, tmp_path, counts)
