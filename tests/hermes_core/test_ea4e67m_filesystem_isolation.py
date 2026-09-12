import ast
from pathlib import Path

import pytest

from tools import ea4e67m_filesystem_guard as guard


def test_forensic_fixture_has_no_filesystem_cleanup():
    source = Path(__file__).with_name("test_opencode_invocation_authorized_live_25a.py").read_text()
    tree = ast.parse(source)
    assert "OPENCODE_SPOOL_DIR" not in source
    assert "AppData" not in source
    assert not any(isinstance(node, ast.Attribute) and node.attr in {
        "rmtree", "unlink", "remove", "rmdir", "makedirs",
    } for node in ast.walk(tree))
    assert "EA4E25A_REAL_EXECUTION_FORBIDDEN" in source


@pytest.mark.parametrize("event,args", [
    ("os.remove", ("live.txt", -1)),
    ("os.rmdir", ("live", -1)),
    ("shutil.rmtree", ("live", None)),
    ("sqlite3.connect", ("live.sqlite3",)),
    ("open", ("live.txt", "w", 0)),
    ("os.rename", ("live.txt", "elsewhere.txt", -1, -1)),
])
def test_live_mutation_is_rejected_before_operation(tmp_path, monkeypatch, event, args):
    monkeypatch.setattr(guard, "_root", tmp_path)
    monkeypatch.setattr(guard, "_active", True)
    monkeypatch.setattr(guard, "_events", [])
    with pytest.raises(RuntimeError, match="EA4E67M_FILESYSTEM_TRIPWIRE"):
        guard.audit(event, args)
    assert len(guard._events) == 1


def test_inside_path_is_admitted_and_parent_escape_is_rejected(tmp_path):
    guard.validate_path(tmp_path / "test.sqlite3", tmp_path)
    with pytest.raises(RuntimeError):
        guard.validate_path(tmp_path / ".." / "live.sqlite3", tmp_path)


def test_sqlite_uri_uses_decoded_path_and_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "_root", tmp_path)
    monkeypatch.setattr(guard, "_active", True)
    monkeypatch.setattr(guard, "_events", [])
    guard.audit("sqlite3.connect", ((tmp_path / "with space.sqlite3").as_uri() + "?mode=rw",))
    with pytest.raises(RuntimeError, match="EA4E67M_FILESYSTEM_TRIPWIRE"):
        guard.audit("sqlite3.connect", ((tmp_path.parent / "live.sqlite3").as_uri() + "?mode=rw",))


def test_null_device_capture_is_not_a_filesystem_write(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(guard, "_root", tmp_path)
    monkeypatch.setattr(guard, "_active", True)
    guard.audit("open", (os.devnull, "w", 0))


def test_real_cleanup_call_is_blocked_and_protected_sentinel_survives(tmp_path, monkeypatch):
    import shutil
    protected = tmp_path / "protected"
    protected.mkdir()
    sentinel = protected / "keep.txt"
    sentinel.write_bytes(b"must remain")
    monkeypatch.setattr(guard, "_root", tmp_path / "allowed")
    monkeypatch.setattr(guard, "_active", True)
    monkeypatch.setattr(guard, "_events", [])
    # Register the guard in a standalone test run too. The process-global hook
    # is inactive after the monkeypatch restores its previous state.
    import sys
    sys.addaudithook(guard.audit)
    with pytest.raises(RuntimeError, match="EA4E67M_FILESYSTEM_TRIPWIRE"):
        shutil.rmtree(protected)
    assert sentinel.read_bytes() == b"must remain"


def test_forensic_fixture_rejects_real_executor_calls(monkeypatch):
    from tests.hermes_core.test_opencode_invocation_authorized_live_25a import forbid_real_execution
    from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
    forbid_real_execution.__wrapped__(monkeypatch)
    with pytest.raises(AssertionError, match="EA4E25A_REAL_EXECUTION_FORBIDDEN"):
        RealOpenCodeProductionExecutor().execute(None)
