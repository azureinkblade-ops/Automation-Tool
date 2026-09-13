"""Fake factory qualification; no real child launch exemption."""

import pytest

from tools import ea4e69_worker_launcher as launch


def test_current_bootstrap_sources_match():
    launch.verify_bootstrap_sources()


def test_source_tamper_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(launch.admission, "ROOT", tmp_path)
    monkeypatch.setattr(launch, "SOURCE_HASHES", {"changed.py": "0" * 64})
    (tmp_path / "changed.py").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="source mismatch"):
        launch.verify_bootstrap_sources()


def setup_admission(monkeypatch):
    def validate(node, argv, cwd, environment, base, admitted):
        if admitted.get(node, 0) >= 1:
            raise ValueError("budget exhausted")
    monkeypatch.setattr(launch.admission, "validate_worker_launch", validate)
    monkeypatch.setattr(launch, "verify_bootstrap_sources", lambda: None)


def test_launch_exact_command_and_owned_registration(monkeypatch):
    setup_admission(monkeypatch)
    calls = []
    child = object()
    launcher = launch.BoundedWorkerLauncher(lambda *args, **kwargs: calls.append((args, kwargs)) or child)
    environment = {"TEMP": "base", "TMP": "base"}
    argv = ["python", "helper", "registry"]
    assert launcher.spawn("node", argv, "cwd", environment, "base") is child
    assert calls[0][0][0] == ["python", "-B", str(launch.admission.ROOT / "tools/ea4e68_worker_entrypoint.py"), "node", "base", *argv]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["env"] == environment
    assert calls[0][1]["env"] is not environment
    assert launcher.owned.children == [child]
    with pytest.raises(ValueError, match="budget"):
        launcher.spawn("node", argv, "cwd", environment, "base")
    assert len(calls) == 1


def test_factory_failure_consumes_attempt(monkeypatch):
    setup_admission(monkeypatch)
    def fail(*args, **kwargs):
        raise OSError("creation failed")
    launcher = launch.BoundedWorkerLauncher(fail)
    with pytest.raises(OSError):
        launcher.spawn("node", ["python", "helper", "registry"], "cwd", {}, "base")
    assert launcher.admitted == {"node": 1}
    assert launcher.owned.children == []


@pytest.mark.parametrize("boundary", ["admission", "source"])
def test_denial_never_calls_factory(monkeypatch, boundary):
    setup_admission(monkeypatch)
    def deny(*args):
        raise ValueError("denied")
    if boundary == "admission":
        monkeypatch.setattr(launch.admission, "validate_worker_launch", deny)
    else:
        monkeypatch.setattr(launch, "verify_bootstrap_sources", deny)
    launcher = launch.BoundedWorkerLauncher(lambda *args, **kwargs: pytest.fail("factory called"))
    with pytest.raises(ValueError, match="denied"):
        launcher.spawn("node", ["python", "helper", "registry"], "cwd", {}, "base")
    assert launcher.admitted == {}


def test_cleanup_delegates_bounded_owned_handle_policy(monkeypatch):
    launcher = launch.BoundedWorkerLauncher(None)
    calls = []
    monkeypatch.setattr(launcher.owned, "cleanup", lambda timeout: calls.append(timeout))
    launcher.cleanup(0.5)
    assert calls == [0.5]
