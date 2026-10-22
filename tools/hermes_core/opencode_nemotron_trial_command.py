"""Fixed, non-executing OpenCode trial command candidate."""

from dataclasses import dataclass

from tools.hermes_core.opencode_adapter import OPENCODE_AGENT_ID


TRIAL_MODEL = "nemotron-3-ultra-free"
TRIAL_TASK = (
    "Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. "
    "Do not use tools or edit files."
)
TRIAL_CONFIG_CANONICAL_SHA256 = (
    "0eaa52c37ab950ce866086754a851052084c1a483107950086deedbea1c05b68"
)


@dataclass(frozen=True)
class NemotronTrialCommand:
    argv: tuple[str, ...]
    config_canonical_sha256: str


def build_nemotron_trial_command() -> NemotronTrialCommand:
    return NemotronTrialCommand(
        argv=(
            "run", "--format", "json", "--pure",
            "--agent", OPENCODE_AGENT_ID,
            "--model", f"opencode/{TRIAL_MODEL}",
            TRIAL_TASK,
        ),
        config_canonical_sha256=TRIAL_CONFIG_CANONICAL_SHA256,
    )
