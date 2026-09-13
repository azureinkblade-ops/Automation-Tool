"""Pure admission tests, never launch an installed process."""
from pathlib import Path
import subprocess

import pytest
from tools.ea4e83_codex_metadata_guard import validate


def options():
    return dict(shell=False, text=True, cwd=str(Path.cwd()), env={"TEMP": "isolated"},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)


def test_exact_metadata_call_admitted():
    value = options()
    validate(["pinned", "--version"], value, ["pinned", "--version"], value["env"], Path.cwd(), 0, 1)


@pytest.mark.parametrize("change", [
    {"shell": True}, {"text": False}, {"cwd": "elsewhere"},
    {"env": {"PATH": "ambient"}}, {"stdin": subprocess.PIPE},
    {"stdout": None}, {"executable": "override"},
])
def test_unsafe_options_denied(change):
    value = options()
    environment = value["env"]
    value.update(change)
    with pytest.raises(ValueError):
        validate(["pinned", "--version"], value, ["pinned", "--version"], environment, Path.cwd(), 0, 1)


def test_task_command_and_exhausted_budget_denied():
    value = options()
    for command, used in [(["pinned", "exec", "task"], 0), (["pinned", "--version"], 1)]:
        with pytest.raises(ValueError):
            validate(command, value, ["pinned", "--version"], value["env"], Path.cwd(), used, 1)
