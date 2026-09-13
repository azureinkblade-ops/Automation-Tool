"""Fake-only sequencing proof; never installs a parent audit hook."""

import runpy

import pytest

from tools import ea4e68_worker_entrypoint as entry
from tools import ea4e67y_worker_admission as admission
from tools import ea4e67z_worker_containment as containment


def test_validation_guard_loading_and_worker_order(monkeypatch):
    events = []
    monkeypatch.setattr(admission, "validate_worker_launch", lambda *args: events.append(("validate", args)))
    monkeypatch.setattr(containment, "install_child_guard", lambda root: events.append(("guard", root)))

    def load(path, run_name):
        events.append(("load", path, run_name))
        return {"main": lambda argv: events.append(("worker", argv)) or 7}

    monkeypatch.setattr(runpy, "run_path", load)
    assert entry.main(["node", "base", "python", "helper", "--reject", "registry"]) == 7
    assert [event[0] for event in events] == ["validate", "guard", "load", "worker"]
    assert events[0][1][1] == ["python", "helper", "--reject", "registry"]
    assert events[-1][1] == ["--reject", "registry"]


@pytest.mark.parametrize("failure", ["validation", "installation"])
def test_failure_never_loads_worker(monkeypatch, failure):
    def deny(*args):
        raise ValueError("denied")

    monkeypatch.setattr(admission, "validate_worker_launch", deny if failure == "validation" else lambda *args: None)
    monkeypatch.setattr(containment, "install_child_guard", deny)
    monkeypatch.setattr(runpy, "run_path", lambda *args, **kwargs: pytest.fail("worker loaded after denial"))
    with pytest.raises(ValueError, match="denied"):
        entry.main(["node", "base", "python", "helper", "registry"])


@pytest.mark.parametrize("argv", [[], ["node"], ["node", "base", "python", "helper"]])
def test_incomplete_envelope_rejected(argv):
    with pytest.raises(ValueError, match="canonical worker argv"):
        entry.main(argv)
