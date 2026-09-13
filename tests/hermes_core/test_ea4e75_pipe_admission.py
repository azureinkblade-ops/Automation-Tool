"""Fake-only byte-stream and process-budget admission proof."""

import os
import subprocess

import pytest

from tools import ea4e75_pipe_matrix_guard as guard


def envelope(tmp_path):
    root = tmp_path / "child"
    root.mkdir()
    node = next(iter(guard.inventory.CASES))
    command = [str(guard.inventory.admission.PYTHON), "-c", guard.inventory.CASES[node][1]]
    opts = dict(cwd=str(root), env={}, shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
    return node, command, opts


def test_exact_byte_pipe_options_admitted(tmp_path):
    node, command, opts = envelope(tmp_path)
    assert guard.validate_call(node, command, opts, tmp_path, {}) == "stdout"


@pytest.mark.parametrize("change", ["budget", "environment", "shell", "stdin", "stdout", "text", "flags"])
def test_unqualified_options_and_budget_denied(tmp_path, change):
    node, command, opts = envelope(tmp_path)
    counts = {}
    if change == "budget":
        counts[node] = 1
    elif change == "environment":
        opts["env"]["API_KEY"] = "not-a-secret"
    elif change == "shell":
        opts["shell"] = True
    elif change == "stdin":
        opts["stdin"] = subprocess.PIPE
    elif change == "stdout":
        opts["stdout"] = None
    elif change == "text":
        opts["text"] = True
    else:
        opts["creationflags"] = -1
    with pytest.raises(ValueError):
        guard.validate_call(node, command, opts, tmp_path, counts)
