"""Token observation never issues authority or launches an elevated process."""

import pytest

from tools.hermes_core import agent_local_docker_operator_token as token


SID = "S-1-5-21-100-200-300-1001"


@pytest.mark.parametrize("observed,elevated,decision,reason", [
    (SID, True, "MATCH", "EXPECTED_ELEVATED_TOKEN_OBSERVED"),
    (SID, False, "DENY", "OPERATOR_TOKEN_NOT_ELEVATED"),
    ("S-1-5-21-100-200-300-1002", True, "DENY", "OPERATOR_SID_MISMATCH"),
])
def test_token_comparison(monkeypatch, observed, elevated, decision, reason):
    monkeypatch.setattr(token, "_read_current_windows_token", lambda: (observed, elevated))
    assert token.check_current_windows_operator_token(SID) == token.OperatorTokenCheck(
        decision, reason,
    )


@pytest.mark.parametrize("sid", [None, "", "david", "S-1-5", 12])
def test_invalid_expected_sid_denied_without_token_read(monkeypatch, sid):
    def forbidden():
        raise AssertionError("token must not be read")
    monkeypatch.setattr(token, "_read_current_windows_token", forbidden)
    assert token.check_current_windows_operator_token(sid).reason == (
        "EXPECTED_OPERATOR_SID_INVALID"
    )


def test_token_read_failure_denied(monkeypatch):
    def failed():
        raise OSError("no token")
    monkeypatch.setattr(token, "_read_current_windows_token", failed)
    assert token.check_current_windows_operator_token(SID).reason == (
        "WINDOWS_TOKEN_UNAVAILABLE"
    )


def test_account_sid_reader_does_not_require_elevation(monkeypatch):
    monkeypatch.setattr(token, "_read_current_windows_token", lambda: (SID, False))
    assert token.read_current_windows_account_sid() == SID


def test_account_sid_reader_denies_malformed_token(monkeypatch):
    monkeypatch.setattr(token, "_read_current_windows_token", lambda: ("bad", True))
    with pytest.raises(OSError, match="malformed"):
        token.read_current_windows_account_sid()
