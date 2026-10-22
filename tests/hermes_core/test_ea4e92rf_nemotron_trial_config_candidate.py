"""Inert model/config candidate checks; no OpenCode process or provider call."""

import json
from pathlib import Path

from tools.hermes_core.opencode_adapter import OPENCODE_AGENT_ID
from tools.hermes_core.opencode_capture_entry import TRIAL_MODEL, TRIAL_TASK


CONFIG = (
    Path(__file__).resolve().parents[2]
    / "tools/hermes_core/fixtures/ea4e92rf_nemotron_trial_config_candidate.json"
)


def test_candidate_is_synthetic_trial_only_and_has_no_credential_material():
    config = json.loads(CONFIG.read_text(encoding="ascii"))
    model = f"opencode/{TRIAL_MODEL}"

    assert set(config) == {
        "$schema", "model", "small_model", "permission", "agent"
    }
    assert config["model"] == config["small_model"] == model
    assert set(config["agent"]) == {OPENCODE_AGENT_ID}
    agent = config["agent"][OPENCODE_AGENT_ID]
    assert set(agent) == {"name", "description", "model", "permission"}
    assert agent["model"] == model
    assert config["permission"] == agent["permission"] == {"*": "deny"}
    assert TRIAL_TASK == (
        b"Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. "
        b"Do not use tools or edit files."
    )
    assert "apiKey" not in CONFIG.read_text(encoding="ascii")
