"""Tests for OpenCode governed receiver adapter — non-live qualification."""

from __future__ import annotations

import json
import os
import pytest

from tools.hermes_core.opencode_adapter import (
    OpenCodeReceiverAdapter,
    OpenCodeParseError,
)


class TestOpenCodeParserCompatibility:
    """Tests for OpenCode JSONL parser compatibility."""

    def test_nested_text_event_accepted(self):
        """Verify nested OpenCode text event is parsed correctly."""
        adapter = OpenCodeReceiverAdapter()
        event = {"type": "text", "part": {"text": "EA4E4_OPENCODE_LIVE_OK"}}
        captured = json.dumps(event)
        result = adapter.parse_output(captured)
        assert result["type"] == "text"
        assert result["text"] == "EA4E4_OPENCODE_LIVE_OK"

    def test_flat_text_event_still_supported(self):
        """Verify flat text event is still supported."""
        adapter = OpenCodeReceiverAdapter()
        event = {"type": "text", "text": "flat text"}
        captured = json.dumps(event)
        result = adapter.parse_output(captured)
        assert result["type"] == "text"
        assert result["text"] == "flat text"

    def test_malformed_nested_part_empty(self):
        """Verify malformed nested event with empty part fails."""
        adapter = OpenCodeReceiverAdapter()
        event = {"type": "text", "part": {}}
        captured = json.dumps(event)
        with pytest.raises(OpenCodeParseError):
            adapter.parse_output(captured)

    def test_malformed_nested_text_null(self):
        """Verify malformed nested event with null text fails."""
        adapter = OpenCodeReceiverAdapter()
        event = {"type": "text", "part": {"text": None}}
        captured = json.dumps(event)
        with pytest.raises(OpenCodeParseError):
            adapter.parse_output(captured)

    def test_malformed_nested_text_object(self):
        """Verify malformed nested event with object text fails."""
        adapter = OpenCodeReceiverAdapter()
        event = {"type": "text", "part": {"text": {"value": "x"}}}
        captured = json.dumps(event)
        with pytest.raises(OpenCodeParseError):
            adapter.parse_output(captured)

    def test_malformed_part_string(self):
        """Verify malformed event with string part fails."""
        adapter = OpenCodeReceiverAdapter()
        event = {"type": "text", "part": "x"}
        captured = json.dumps(event)
        with pytest.raises(OpenCodeParseError):
            adapter.parse_output(captured)

    def test_error_event_semantics_preserved(self):
        """Verify error event handling is unchanged."""
        adapter = OpenCodeReceiverAdapter()
        event = {"type": "error", "error": {"message": "test error"}}
        captured = json.dumps(event)
        result = adapter.parse_output(captured)
        assert result["type"] == "error"

    def test_unknown_event_type_rejected(self):
        """Verify unknown event types cause parse error."""
        adapter = OpenCodeReceiverAdapter()
        event = {"type": "unknown_event"}
        captured = json.dumps(event)
        with pytest.raises(OpenCodeParseError):
            adapter.parse_output(captured)

    def test_offline_replay_captured_live_jsonl(self):
        """Verify exact captured EA-4E.4 JSONL replays correctly."""
        adapter = OpenCodeReceiverAdapter()
        spool_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Hermes", "runtime", "ea4e", "opencode", "spool",
            "run-d1eca109.stdout.jsonl"
        )
        with open(spool_path, "r") as f:
            captured = f.read()
        result = adapter.parse_output(captured)
        assert result["type"] == "text"
        assert result["text"] == "EA4E4_OPENCODE_LIVE_OK"
