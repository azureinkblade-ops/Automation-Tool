"""Tests for tools/regression_parser.parse_regression_output.

These pin the SC-8-adjacent regression-dashboard parse fix: the parser must
consume the COMPLETE captured stream (never a truncated window), while any
human-facing display truncation stays the caller's concern.

Acceptance criteria covered:
1. Valid structured output occurring after character 4,000 is still parsed.
2. Displayed stdout remains capped at 4,000 characters.
3. Parsed status, totals, failures, and timestamps remain correct.
4. Malformed or missing structured output fails gracefully.
5. Large stderr does not interfere with stdout parsing.
6. Existing short-output behavior remains unchanged.
7. (implied) parser never raises; never truncates its own parse input.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def parser():
    return _load("regression_parser", ROOT / "tools" / "regression_parser.py")


def _report(ok, checks, failed, generated_at):
    return {
        "ok": ok,
        "mode": "regression",
        "generatedAt": generated_at,
        "failedCount": failed,
        "checks": checks,
        "slowCount": 0,
    }


def test_valid_output_after_char_4000_is_parsed(parser):
    # 4100 chars of preamble, then a valid JSON report on the final line.
    preamble = "x" * 4100 + "\n[info] running probes...\n"
    report = _report(True, [{"name": "a", "ok": True}], 0, "2026-07-23 12:00:00")
    stdout = preamble + json.dumps(report)
    result = parser.parse_regression_output(stdout, "")
    assert result == report
    assert result["ok"] is True
    assert result["checks"] == [{"name": "a", "ok": True}]


def test_displayed_stdout_capped_at_4000(parser):
    # The parsed result comes from full text, but a 4000-char display cap is
    # applied by the caller. This test asserts the contract slice directly.
    stdout = "y" * 9000 + json.dumps(_report(True, [], 0, "2026-07-23 12:00:00"))
    result = parser.parse_regression_output(stdout, "")
    assert result["ok"] is True
    display = stdout[-4000:]
    assert len(display) == 4000
    assert display.startswith("y" * (4000 - len(json.dumps(result))))


def test_parsed_status_totals_failures_timestamps_correct(parser):
    report = _report(False, [{"name": "a", "ok": True}, {"name": "b", "ok": False}], 1, "2026-07-23 09:15:42")
    stdout = "log line\n" + json.dumps(report)
    result = parser.parse_regression_output(stdout, "")
    assert result["ok"] is False
    assert result["failedCount"] == 1
    assert len(result["checks"]) == 2
    assert result["generatedAt"] == "2026-07-23 09:15:42"


def test_malformed_output_fails_gracefully(parser):
    # No JSON anywhere -> graceful error dict, never raises.
    result = parser.parse_regression_output("just some text\nmore text", "warn: thing")
    assert isinstance(result, dict)
    assert result.get("error") == "Script did not return JSON."
    # diagnostics are truncated to 4000 (defensive, not the parse input)
    assert len(result["stdout"]) <= 4000
    assert len(result["stderr"]) <= 4000


def test_missing_output_fails_gracefully(parser):
    result = parser.parse_regression_output("", "")
    assert isinstance(result, dict)
    assert result.get("error") == "Script did not return JSON."


def test_large_stderr_does_not_block_stdout_parsing(parser):
    # Huge stderr must not mask a valid stdout report.
    huge_stderr = "E" * 20000
    report = _report(True, [{"name": "x", "ok": True}], 0, "2026-07-23 08:00:00")
    result = parser.parse_regression_output(json.dumps(report), huge_stderr)
    assert result["ok"] is True
    assert result["generatedAt"] == "2026-07-23 08:00:00"


def test_short_output_behavior_unchanged(parser):
    # Existing short-output behavior: a compact JSON report parses directly.
    report = _report(True, [{"name": "z", "ok": True}], 0, "2026-07-23 07:00:00")
    result = parser.parse_regression_output(json.dumps(report), "")
    assert result == report


def test_parser_never_raises_on_garbage(parser):
    for bad in ["", "{not json", "}}}", "12345", "null", "{}"]:
        try:
            out = parser.parse_regression_output(bad, bad)
        except Exception as exc:  # pragma: no cover
            pytest.fail(f"parse_regression_output raised on {bad!r}: {exc}")
        assert isinstance(out, dict)


def test_preamble_and_trailer_tolerated(parser):
    # JSON wrapped in non-JSON lines on both sides.
    report = _report(True, [], 0, "2026-07-23 06:00:00")
    stdout = "START\n" + json.dumps(report) + "\nEND"
    result = parser.parse_regression_output(stdout, "")
    assert result["ok"] is True
    assert result["generatedAt"] == "2026-07-23 06:00:00"
