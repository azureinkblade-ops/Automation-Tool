# EA-4E.92RG Nemotron Trial Command Candidate

Status: SOURCE-ONLY / NON-EXECUTING / NOT INSTALLED.
Source baseline: `4dc0d1c95bbbec6233b652766666a148665928d2`.

`tools/hermes_core/opencode_nemotron_trial_command.py` constructs an inert
argument tuple for `opencode run`: JSON output, `--pure`, the EA-4E receiver
agent, explicit `--model opencode/nemotron-3-ultra-free`, and the frozen
synthetic 92GQ trial task. It binds the canonical semantic hash of the 92RF
config candidate. It starts no process and is not wired into the active
adapter. This explicit model flag is required by the pinned OpenCode 1.18.11
source contract; the older qualified adapter omits it and remains unchanged.

The 92RG, 92RF, and 92GS focused tests passed 28/28 with stage2-v2 Python,
strict non-live gating, workspace-local temporary files, and worktree-confined
pytest collection. Broader adjacent 92GQ attempts did not pass: Windows
denied `os.replace` of a SQLite capture-store anchor in pre-existing tests.
Those attempts made no receiver or provider call; they are not represented
as a green regression suite. The 92RF committed-tree suite previously passed
105/105, but that does not resolve this later filesystem failure.

`--pure` does not disable built-in tools, networking, or config merging.
This source candidate is not an effective merged-config observation or
authorization to run OpenCode. Protected one-use issuance, installed config,
credential reference, egress and call accounting, exact live-call approval,
and a real handoff remain unqualified. Production remains HOLD.
