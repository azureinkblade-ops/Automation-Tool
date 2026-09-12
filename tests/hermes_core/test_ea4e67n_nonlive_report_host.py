import platform

import pytest

from tools.ea4e67n_nonlive_report_host import REPORT_HOST, pytest_sessionfinish as report_hook


def test_report_metadata_has_explicit_synthetic_host_and_restores_original(monkeypatch):
    original = lambda: "original"
    monkeypatch.setattr(platform, "node", original)
    hook = report_hook(None, 0)
    next(hook)
    assert platform.node() == REPORT_HOST
    with pytest.raises(StopIteration):
        next(hook)
    assert platform.node is original


def test_report_metadata_restores_original_on_report_failure(monkeypatch):
    original = lambda: "original"
    monkeypatch.setattr(platform, "node", original)
    hook = report_hook(None, 0)
    next(hook)
    with pytest.raises(RuntimeError, match="report failed"):
        hook.throw(RuntimeError("report failed"))
    assert platform.node is original
