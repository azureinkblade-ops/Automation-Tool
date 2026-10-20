"""Process-local, fake-only one-use accounting for an announcement record."""

from tools.ea4e92oj_pipe_announcement import (
    AnnouncementDenied, ExpectedAnnouncement, decode_announcement,
)


class InertAnnouncementLease:
    """Deny repeated or ambiguous handoffs in one process lifetime only."""

    def __init__(self, expected, *, fake_only):
        if type(expected) is not ExpectedAnnouncement or fake_only is not True:
            raise AnnouncementDenied("native announcement authority unavailable")
        self._expected = expected
        self.state = "NEW"

    def consume(self, raw, *, now_unix_ms):
        if self.state != "NEW":
            raise AnnouncementDenied("announcement lease already consumed")
        self.state = "UNKNOWN"
        record = decode_announcement(raw, expected=self._expected,
                                     now_unix_ms=now_unix_ms)
        self.state = "CONSUMED"
        return record

    def close(self):
        if self.state == "CLOSED":
            raise AnnouncementDenied("announcement lease already closed")
        self.state = "CLOSED"
