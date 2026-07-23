"""Pure regression/test-script output parser.

This module exists so that the regression dashboard (and any other caller) can
parse a subprocess report from the COMPLETE captured stream, independent of any
human-facing display truncation.

Historically the parse happened against a field that had already been sliced to
a bounded preview (e.g. ``stdout[-4000:]``) or reduced to ``splitlines()[-1]``.
When a test script emits thousands of lines of preamble before its final JSON
report, that windowing silently dropped the structured result and the dashboard
fell back to an error payload.

Contract:
- The parser is fed the UNTRUNCATED stdout/stderr. Display truncation is the
  caller's concern, never the parser's.
- It prefers stdout, then falls back to stderr (so a large stderr does not
  prevent parsing a valid stdout report, and vice versa).
- It tolerates a stray non-JSON preamble/trailer by slicing from the first '{'
  to the last '}'.
- On malformed or missing structured output it returns a graceful error dict
  (no exception is raised), keeping the dashboard resilient.
"""
from __future__ import annotations

import json


def _parse_text(text: str) -> dict | None:
    """Return parsed JSON dict from text, or None if not parseable."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    # Tolerate a leading/trailing non-JSON preamble: take the outermost {...}.
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
    except Exception:
        pass
    return None


def parse_regression_output(full_stdout: str, full_stderr: str = "") -> dict:
    """Parse a regression/test-script JSON report from the full captured stream.

    Args:
        full_stdout: complete stdout of the subprocess (NOT truncated).
        full_stderr: complete stderr of the subprocess (NOT truncated).

    Returns:
        The parsed report dict, or a graceful error dict when no structured
        output could be found. The error dict's ``stdout``/``stderr`` fields are
        truncated to 4000 chars purely for diagnostics; the parse input itself
        is never truncated here.
    """
    stdout = (full_stdout or "").strip()
    stderr = (full_stderr or "").strip()

    # Prefer stdout; fall back to stderr. A large stderr must not mask a valid
    # stdout report, and a large stdout preamble must not mask a stderr report.
    for text in (stdout, stderr):
        parsed = _parse_text(text)
        if isinstance(parsed, dict):
            return parsed

    return {
        "error": "Script did not return JSON.",
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
    }
