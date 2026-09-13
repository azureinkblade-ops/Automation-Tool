"""Fake-only exact-input and deterministic output equivalence tests."""

from io import StringIO
import ast
import sys
import time

import pytest

from tools import ea4e67z_worker_containment as containment
from tools import ea4e74_pipe_inventory as inventory
from tools import ea4e74_pipe_probe as probe


def test_inventory_matches_original_test_source():
    source = (inventory.admission.ROOT / "tests/hermes_core/test_opencode_adapter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = set()
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for fn in cls.body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            node = inventory.PREFIX + cls.name + "::" + fn.name
            if node not in inventory.CASES:
                continue
            calls = [item for item in ast.walk(fn) if isinstance(item, ast.Call)
                     and isinstance(item.func, ast.Name) and item.func.id == "OpenCodeArgv"]
            assert len(calls) == 1
            argument = next(item.value for item in calls[0].keywords if item.arg == "args")
            case, snippet = inventory.CASES[node]
            if snippet is not None:
                assert ast.literal_eval(argument) == ("-c", snippet)
            else:
                writes = [item for item in ast.walk(fn) if isinstance(item, ast.Call)
                          and isinstance(item.func, ast.Attribute) and item.func.attr == "write_text"]
                assert len(writes) == 1
                assert ast.literal_eval(writes[0].args[0]) == inventory.MALFORMED_SOURCE
            found.add(node)
    assert found == set(inventory.CASES)


@pytest.mark.parametrize("node", list(inventory.CASES))
def test_exact_original_input_admitted(tmp_path, node):
    root = tmp_path / "child"
    root.mkdir()
    case, snippet = inventory.CASES[node]
    if snippet is None:
        script = root / "malformed.py"
        script.write_text(inventory.MALFORMED_SOURCE, encoding="utf-8")
        args = [str(script)]
    else:
        args = ["-c", snippet]
    assert inventory.pipe_case(node, [str(inventory.admission.PYTHON), *args], root, tmp_path) == case


@pytest.mark.parametrize("change", ["node", "executable", "snippet", "flag", "root", "extra"])
def test_other_inputs_denied(tmp_path, change):
    root = tmp_path / "child"
    root.mkdir()
    node = next(iter(inventory.CASES))
    command = [str(inventory.admission.PYTHON), "-c", inventory.CASES[node][1]]
    if change == "node":
        node = "other"
    elif change == "executable":
        command[0] = "opencode.exe"
    elif change == "snippet":
        command[2] += "; other()"
    elif change == "flag":
        command[1] = "-m"
    elif change == "root":
        root = tmp_path
    else:
        command.append("other")
    with pytest.raises(ValueError):
        inventory.pipe_case(node, command, root, tmp_path)


OUTPUTS = {
    "stdout": ("EA4E_PIPE_STDOUT_OK\n", "", []),
    "stderr": ("", "EA4E_PIPE_STDERR_OK\n", []),
    "dual": ("STDOUT_MARKER\n", "STDERR_MARKER\n", []),
    "large": ("X" * 200000, "", []),
    "empty": ("", "", []),
    "timeout": ("", "", [30]),
    "stdout_overflow": ("X" * (4 * 1024 * 1024), "", []),
    "stderr_overflow": ("", "Y" * (1024 * 1024), []),
    "dual_overflow": ("A" * (2 * 1024 * 1024), "B" * (512 * 1024), []),
    "reader_stuck": ("X" * 100, "", []),
    "reader_error": ("X" * 100, "", []),
    "success": ("EA4E_SUCCESS\n", "", []),
    "raw": ("C" * (2 * 1024 * 1024), "", []),
    "malformed": ("not json{{{invalid\n", "", []),
    "cancel": ("", "", [60]),
}


@pytest.mark.parametrize("case", list(OUTPUTS))
def test_helper_output_matches_original_workload(tmp_path, monkeypatch, case):
    out, err, sleeps, guards = StringIO(), StringIO(), [], []
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    monkeypatch.setattr(containment, "install_child_guard", guards.append)
    assert probe.main(case, tmp_path) == 0
    assert (out.getvalue(), err.getvalue(), sleeps) == OUTPUTS[case]
    assert guards == [tmp_path]


def test_unknown_helper_case_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(containment, "install_child_guard", lambda root: None)
    with pytest.raises(ValueError, match="unqualified"):
        probe.main("other", tmp_path)
