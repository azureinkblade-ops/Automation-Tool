"""Fake-only in-process replay accounting; no native handle or pipe."""

import pytest

from tools.ea4e92oj_pipe_announcement import AnnouncementDenied
from tools.ea4e92ok_announcement_lease import InertAnnouncementLease
from tests.hermes_core.test_ea4e92oj_pipe_announcement import (
    EXPECTED, RECORD, encoded,
)


def test_one_inert_handoff_then_replay_denied():
    lease = InertAnnouncementLease(EXPECTED, fake_only=True)
    assert lease.state == "NEW"
    assert lease.consume(encoded(RECORD), now_unix_ms=110000).pipe_name == RECORD["pipe_name"]
    assert lease.state == "CONSUMED"
    with pytest.raises(AnnouncementDenied, match="already consumed"):
        lease.consume(encoded(RECORD), now_unix_ms=110001)
    assert lease.state == "CONSUMED"
    lease.close()
    assert lease.state == "CLOSED"


def test_invalid_first_record_poisoned_without_retry():
    lease = InertAnnouncementLease(EXPECTED, fake_only=True)
    with pytest.raises(AnnouncementDenied):
        lease.consume(b"{}", now_unix_ms=110000)
    assert lease.state == "UNKNOWN"
    with pytest.raises(AnnouncementDenied, match="already consumed"):
        lease.consume(encoded(RECORD), now_unix_ms=110000)
    lease.close()
    assert lease.state == "CLOSED"


@pytest.mark.parametrize("fake_only", [False, None, 1, "true"])
def test_no_native_mode(fake_only):
    with pytest.raises(AnnouncementDenied, match="native announcement authority unavailable"):
        InertAnnouncementLease(EXPECTED, fake_only=fake_only)


def test_closed_before_use_cannot_consume():
    lease = InertAnnouncementLease(EXPECTED, fake_only=True)
    lease.close()
    with pytest.raises(AnnouncementDenied, match="already consumed"):
        lease.consume(encoded(RECORD), now_unix_ms=110000)
    with pytest.raises(AnnouncementDenied, match="already closed"):
        lease.close()
