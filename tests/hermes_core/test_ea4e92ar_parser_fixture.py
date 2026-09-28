"""Fake-only fixture contract checks; Node is never launched."""

import json
from pathlib import Path

import pytest

from tools import ea4e92ar_parser_capture as subject


FIXTURE = Path(__file__).resolve().parents[2] / "tools" / "ea4e92ar_argv_fixture.js"
ARGV = (
    r"C:\Program Files\Node\node.exe",
    r"C:\request root\argv fixture.js",
    "--probe-id", "NQ-01",
    "--request-id", "probe-123",
    "--request", r"C:\request root\request.json",
)


def capture(argv=ARGV, **changes):
    record = {"schemaVersion": 1, "argv": list(argv)}
    record.update(changes)
    return (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def test_fixture_source_is_exact_inert_one_record_writer():
    assert FIXTURE.read_text(encoding="ascii") == (
        '"use strict";\n'
        'process.stdout.write(JSON.stringify({schemaVersion:1,argv:process.argv})+"\\n");\n'
    )


def test_exact_offline_capture_accepted():
    assert subject.parse_fixture_stdout(capture(), ARGV) == ARGV


def test_unicode_and_quotes_preserved():
    argv = ARGV[:-1] + ('C:\\\u96ea\\a "quoted" \U0001f642.json',)
    assert subject.parse_fixture_stdout(capture(argv), argv) == argv


@pytest.mark.parametrize("raw", [
    b"", b"not json\n", b"{\"schemaVersion\":1,\"argv\":[]}\n",
    b'{"schemaVersion":1,"argv":[],"argv":[]}\n',
    b'{"schemaVersion":1,"argv":[]}\n{"schemaVersion":1,"argv":[]}\n',
    b'{"schemaVersion":1,"argv":[]}\n\n',
    b"\xff", b"\xef\xbb\xbf" + capture(),
    b"X" * (subject.MAX_STDOUT_BYTES + 1),
    None,
], ids=[
    "empty", "not-json", "wrong-shape", "duplicate-key", "two-records",
    "blank-line", "bad-utf8", "bom", "too-large", "none",
])
def test_malformed_or_ambiguous_capture_denied(raw):
    with pytest.raises(ValueError):
        subject.parse_fixture_stdout(raw, ARGV)


@pytest.mark.parametrize("raw", [
    capture(argv=ARGV[:-1] + ("other.json",)),
    capture(argv=ARGV[:-1]),
    capture(argv=ARGV + ("extra",)),
    capture(schemaVersion=2),
    capture(argv=[*ARGV[:-1], 1]),
    capture(extra=True),
])
def test_schema_or_argv_drift_denied(raw):
    with pytest.raises(ValueError):
        subject.parse_fixture_stdout(raw, ARGV)


def test_expected_argv_must_be_exact_eight_strings():
    for expected in (list(ARGV), ARGV[:-1], ARGV + ("extra",), ARGV[:-1] + (1,)):
        with pytest.raises(ValueError):
            subject.parse_fixture_stdout(capture(), expected)


def test_offline_parser_has_no_runtime_binding():
    source = Path(subject.__file__).read_text(encoding="ascii")
    for forbidden in ("subprocess", "CreateProcess", "WinDLL", "socket", "requests"):
        assert forbidden not in source
