"""Focused malformed-Hermes-output classification and observability tests."""

from __future__ import annotations

import json
import logging
import subprocess

import automation_db
from tools import agent_post_writer as writer


VALID = {
    "hook": "A system wakes in the rain.",
    "caption": "Kael hears the offer and realizes it already knows his name.",
    "cta": "Read Eternal Nexus.",
    "hashtags": ["#EternalNexus", "#AzureInkblade"],
    "content_angle": "system betrayal",
    "intended_audience": "progression fantasy readers",
}


class _Proc:
    def __init__(self, stdout: str = "", *, returncode: int = 0, stderr: str = ""):
        self.stdout = stdout.encode("utf-8")
        self.stderr = stderr.encode("utf-8")
        self.returncode = returncode


class _Messages(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _run(monkeypatch, stdout: str = "", *, exception: Exception | None = None):
    monkeypatch.setattr(writer, "_resolve_hermes", lambda: r"C:\fake\hermes.exe")
    monkeypatch.setattr(automation_db, "insert_agent_post_run", lambda *a, **k: None)
    monkeypatch.setattr(automation_db, "replace_agent_post_fields", lambda *a, **k: None)

    if exception is not None:
        def invoke(*args, **kwargs):
            raise exception
    else:
        def invoke(*args, **kwargs):
            return _Proc(stdout)
    monkeypatch.setattr(writer.subprocess, "run", invoke)

    handler = _Messages()
    writer._logger.addHandler(handler)
    try:
        result = writer.generate_post_result(
            "EN", "Eternal Nexus", "37", "neon rain", {"text": "fixture"}
        )
    finally:
        writer._logger.removeHandler(handler)
    return result, writer.agent_result_metadata(result), handler.messages


def _json_with(**updates) -> str:
    payload = dict(VALID)
    payload.update(updates)
    return json.dumps(payload)


def test_valid_json_is_distinct_from_repaired_json(monkeypatch):
    result, meta, logs = _run(monkeypatch, _json_with())

    assert result.status is writer.AgentPostStatus.SUCCESS
    assert result.parse_mode == "whole_text"
    assert meta["_agent_outcome"] == "valid_json"
    assert meta["_agent_fallback_activated"] is False
    assert any("OUTCOME=valid_json" in line for line in logs)


def test_doubled_value_side_quotes_are_repaired_and_observable(monkeypatch):
    malformed = _json_with().replace(
        '"caption": "Kael hears the offer and realizes it already knows his name."',
        '"caption": ""Kael hears the offer and realizes it already knows his name.""',
    )
    result, meta, logs = _run(monkeypatch, malformed)

    assert result.status is writer.AgentPostStatus.SUCCESS
    assert result.copy["caption"].startswith("Kael hears")
    assert "collapsed_double_quotes" in result.normalizations
    assert meta["_agent_outcome"] == "repaired_json"
    assert "collapsed_double_quotes" in meta["_agent_parse_normalizations"]
    assert any("OUTCOME=repaired_json" in line for line in logs)


def test_unquoted_hashtag_elements_are_repaired(monkeypatch):
    malformed = _json_with().replace(
        '["#EternalNexus", "#AzureInkblade"]',
        '[#EternalNexus, #AzureInkblade"]',
    )
    result, meta, _ = _run(monkeypatch, malformed)

    assert result.status is writer.AgentPostStatus.SUCCESS
    assert result.copy["hashtags"] == ["#EternalNexus", "#AzureInkblade"]
    assert "quoted_unquoted_hashtag_elements" in meta["_agent_parse_normalizations"]


def test_comments_and_trailing_commas_are_repaired(monkeypatch):
    malformed = _json_with().replace(
        '"cta": "Read Eternal Nexus.",',
        '"cta": "Read Eternal Nexus.", // keep the CTA separate\n',
    ).replace(
        '"intended_audience": "progression fantasy readers"',
        '"intended_audience": "progression fantasy readers", /* trailing note */',
    )
    result, meta, _ = _run(monkeypatch, malformed)

    assert result.status is writer.AgentPostStatus.SUCCESS
    assert set(meta["_agent_parse_normalizations"]) >= {
        "removed_line_comment",
        "removed_block_comment",
        "removed_trailing_comma",
    }


def test_truncated_json_is_unrecoverable_and_activates_fallback(monkeypatch):
    truncated = _json_with()[:-24]
    result, meta, logs = _run(monkeypatch, truncated)

    assert result.status is writer.AgentPostStatus.JSON_PARSE_FAILED
    assert result.copy is None
    assert meta["_agent_outcome"] == "unrecoverable_json"
    assert meta["_agent_fallback_activated"] is True
    assert meta["_agent_response_chars"] == len(truncated)
    assert meta["_agent_response_sha256"]
    assert any("generic_template_fallback=true" in line.lower() for line in logs)


def test_wrong_shaped_json_is_invalid_contract(monkeypatch):
    result, meta, _ = _run(monkeypatch, '["caption", "not an object"]')

    assert result.status is writer.AgentPostStatus.CONTRACT_VALIDATION_FAILED
    assert meta["_agent_outcome"] == "invalid_contract"
    assert meta["_agent_fallback_activated"] is True
    assert "payload is not a JSON object" in meta["_agent_validation_errors"]
    assert set(writer._REQUIRED_FIELDS) <= set(meta["_agent_missing_fields"])


def test_empty_response_is_classified_separately(monkeypatch):
    result, meta, logs = _run(monkeypatch, "")

    assert result.status is writer.AgentPostStatus.HERMES_EMPTY_OUTPUT
    assert meta["_agent_outcome"] == "empty_response"
    assert meta["_agent_fallback_activated"] is True
    assert any("OUTCOME=empty_response" in line for line in logs)


def test_invocation_exception_is_bounded_and_classified(monkeypatch):
    secret = "do-not-log-provider-token"
    result, meta, logs = _run(monkeypatch, exception=OSError(secret))
    joined = "\n".join(logs)

    assert result.status is writer.AgentPostStatus.HERMES_PROCESS_FAILED
    assert meta["_agent_outcome"] == "invocation_failure"
    assert meta["_agent_fallback_activated"] is True
    assert result.fallback_reason == "hermes subprocess error: OSError"
    assert secret not in joined
    assert "OUTCOME=invocation_failure" in joined
