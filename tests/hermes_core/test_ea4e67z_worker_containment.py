import io
import os
import subprocess

import pytest

from tools.ea4e67z_worker_containment import OwnedChildren, child_audit_policy


@pytest.mark.parametrize("event", ["subprocess.Popen", "socket.connect", "os.system", "os.exec", "os.spawn", "os.fork", "ctypes.dlopen"])
def test_child_rejects_capabilities(tmp_path, event):
    with pytest.raises(RuntimeError):
        child_audit_policy(tmp_path)(event, ())


@pytest.mark.parametrize("event", ["open", "sqlite3.connect", "os.mkdir", "os.remove", "os.rename"])
def test_child_mutation_paths(tmp_path, event):
    audit = child_audit_policy(tmp_path)
    inside = str(tmp_path / "state.sqlite")
    outside = str(tmp_path.parent / "protected.sqlite")
    def args(path):
        if event == "open":
            return path, "w", os.O_WRONLY
        if event == "os.rename":
            return inside, path
        return (path,)
    audit(event, args(inside))
    with pytest.raises(RuntimeError):
        audit(event, args(outside))


def test_child_sqlite_uri_rejected(tmp_path):
    with pytest.raises(RuntimeError):
        child_audit_policy(tmp_path)("sqlite3.connect", ("file://remote/state.sqlite",))


class FakeChild:
    def __init__(self, stuck=False):
        self.alive = True
        self.stuck = stuck
        self.calls = []
        self.stdin, self.stdout, self.stderr = io.StringIO(), io.StringIO(), io.StringIO()

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")
        if not self.stuck:
            self.alive = False

    def wait(self, timeout):
        self.calls.append("wait")
        if self.alive:
            raise subprocess.TimeoutExpired("fake-owned-child", timeout)
        return 0


def test_owned_cleanup_kills_reaps_and_closes():
    owned = OwnedChildren()
    child = FakeChild()
    owned.register(child)
    owned.cleanup()
    assert child.calls == ["terminate", "wait", "kill", "wait"]
    assert child.poll() == 0
    assert all(pipe.closed for pipe in (child.stdin, child.stdout, child.stderr))


def test_cleanup_continues_after_failure():
    owned = OwnedChildren()
    stuck, healthy = FakeChild(stuck=True), FakeChild()
    owned.register(stuck)
    owned.register(healthy)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        owned.cleanup()
    assert healthy.poll() == 0
    assert all(pipe.closed for child in (stuck, healthy) for pipe in (child.stdin, child.stdout, child.stderr))


@pytest.mark.parametrize("timeout", [0, -1, 4, float("nan"), float("inf")])
def test_cleanup_requires_bounded_timeout(timeout):
    with pytest.raises(ValueError):
        OwnedChildren().cleanup(timeout)
