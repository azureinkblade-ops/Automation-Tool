"""No processes or real descriptor writes; rule and scope unit tests."""

import os
import subprocess
import threading
from types import SimpleNamespace

import pytest

from tools.ea4e71_owned_pipe_scope import OwnedPipeScope


def envelope():
    code = object()
    scope = OwnedPipeScope(code)
    frame = SimpleNamespace(f_code=code, f_locals={"p2cwrite": 17, "stdin": subprocess.PIPE,
                                                  "self": SimpleNamespace(args=["frozen"])} )
    return scope, frame


def test_owned_stdin_only_inside_creation():
    scope, frame = envelope()
    args = (17, "w", os.O_WRONLY)
    assert not scope.allows("open", args, frame)
    with scope.creation(["frozen"]):
        assert scope.allows("open", args, frame)
    assert not scope.allows("open", args, frame)


@pytest.mark.parametrize("args", [(18, "w", os.O_WRONLY), (17, "r", os.O_RDONLY),
                                  (17, "w+", os.O_RDWR), ("file", "w", os.O_WRONLY),
                                  (True, "w", os.O_WRONLY), (17, "w", os.O_RDWR)])
def test_unrelated_descriptor_mode_and_path_denied(args):
    scope, frame = envelope()
    with scope.creation(["frozen"]):
        assert not scope.allows("open", args, frame)


@pytest.mark.parametrize("change", ["code", "command", "stdin", "event"])
def test_changed_call_boundary_denied(change):
    scope, frame = envelope()
    event = "open"
    if change == "code":
        frame.f_code = object()
    elif change == "command":
        frame.f_locals["self"].args = ["other"]
    elif change == "stdin":
        frame.f_locals["stdin"] = 17
    else:
        event = "os.remove"
    with scope.creation(["frozen"]):
        assert not scope.allows(event, (17, "w", os.O_WRONLY), frame)


def test_other_thread_and_exception_escape_denied():
    scope, frame = envelope()
    results = []
    with pytest.raises(ValueError):
        with scope.creation(["frozen"]):
            thread = threading.Thread(target=lambda: results.append(scope.allows("open", (17, "w", os.O_WRONLY), frame)))
            thread.start()
            thread.join(timeout=1)
            assert not thread.is_alive()
            raise ValueError("leave scope")
    assert results == [False]
    assert not scope.allows("open", (17, "w", os.O_WRONLY), frame)


def test_nested_scope_rejected_without_losing_outer_scope():
    scope, frame = envelope()
    with scope.creation(["frozen"]):
        with pytest.raises(RuntimeError, match="nested"):
            with scope.creation(["other"]):
                pass
        assert scope.allows("open", (17, "w", os.O_WRONLY), frame)
