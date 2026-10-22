"""Pure command-spec checks; no receiver or provider execution."""

import hashlib
import json
from pathlib import Path

from tools.hermes_core.opencode_nemotron_trial_command import (
    TRIAL_MODEL,
    TRIAL_TASK,
    TRIAL_CONFIG_CANONICAL_SHA256,
    build_nemotron_trial_command,
)
from tools.hermes_core.opencode_capture_entry import (
    TRIAL_MODEL as CAPTURE_TRIAL_MODEL,
    TRIAL_TASK as CAPTURE_TRIAL_TASK,
)


CONFIG = (
    Path(__file__).resolve().parents[2]
    / "tools/hermes_core/fixtures/ea4e92rf_nemotron_trial_config_candidate.json"
)


def test_trial_command_binds_explicit_model_agent_and_synthetic_task():
    spec = build_nemotron_trial_command()
    assert spec.argv == (
        "run", "--format", "json", "--pure",
        "--agent", "hermes-ea4e-opencode-receiver",
        "--model", "opencode/nemotron-3-ultra-free",
        "Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. "
        "Do not use tools or edit files.",
    )
    assert "--auto" not in spec.argv
    assert "--command" not in spec.argv
    assert TRIAL_MODEL == CAPTURE_TRIAL_MODEL
    assert TRIAL_TASK.encode("ascii") == CAPTURE_TRIAL_TASK


def test_trial_command_binds_candidate_config_semantics():
    config = json.loads(CONFIG.read_text(encoding="ascii"))
    raw = json.dumps(config, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True).encode("ascii")
    assert hashlib.sha256(raw).hexdigest() == TRIAL_CONFIG_CANONICAL_SHA256
    assert build_nemotron_trial_command().config_canonical_sha256 == (
        TRIAL_CONFIG_CANONICAL_SHA256
    )
