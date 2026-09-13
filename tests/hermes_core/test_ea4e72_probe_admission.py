"""Fake-only call admission proof; does not activate the one-child plugin."""

import os
import subprocess

import pytest

from tools import ea4e72_child_probe_guard as guard


def envelope(tmp_path):
    root = tmp_path / "child"
    root.mkdir()
    env = {name: os.environ[name] for name in ("SYSTEMROOT", "SYSTEMDRIVE") if name in os.environ}
    env.update(TEMP=str(root), TMP=str(root))
    command = [str(guard.admission.PYTHON), "-B", str(guard.HELPER), str(root)]
    options = dict(cwd=guard.admission.ROOT, env=env, shell=False, stdin=subprocess.PIPE,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    return command, options


def test_current_sources_match():
    guard.verify_sources()


def test_exact_probe_admitted(tmp_path):
    command, options = envelope(tmp_path)
    guard.validate_call(command, options, tmp_path, guard.NODE, 0)


@pytest.mark.parametrize("change", ["node", "budget", "executable", "helper", "flags", "shell", "environment", "root", "stdin", "cwd"])
def test_unqualified_call_denied(tmp_path, change):
    command, options = envelope(tmp_path)
    node, attempts = guard.NODE, 0
    if change == "node":
        node = "other"
    elif change == "budget":
        attempts = 1
    elif change == "executable":
        command[0] = "other"
    elif change == "helper":
        command[2] = "other"
    elif change == "flags":
        command[1] = "-c"
    elif change == "shell":
        options["shell"] = True
    elif change == "environment":
        options["env"]["API_KEY"] = "not-a-secret"
    elif change == "root":
        command[3] = str(tmp_path)
    elif change == "stdin":
        options["stdin"] = None
    else:
        options["cwd"] = tmp_path
    with pytest.raises(ValueError):
        guard.validate_call(command, options, tmp_path, node, attempts)
