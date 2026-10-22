# EA-4E.92RF Nemotron Trial Config Candidate

Status: INERT CONFIG CANDIDATE / SOURCE-ONLY TEST PASS / NOT INSTALLED.
Source baseline: `7dedce8c1ed34340652434517f4785c791972d54`.

The exact candidate at
`tools/hermes_core/fixtures/ea4e92rf_nemotron_trial_config_candidate.json`
selects `opencode/nemotron-3-ultra-free` for the default, small, and
`hermes-ea4e-opencode-receiver` agent models. Top-level and agent tool
permissions are `* = deny`. It has no provider credential or provider
definition. It is a source fixture, not an active runtime config or
qualified merged-config observation. The existing isolated
`config/config.json` was left unchanged at its Ollama pin.

The candidate agrees with the existing 92GQ synthetic trial task and
`nemotron-3-ultra-free` request model. Focused candidate, canonical binding,
and capture-entry tests passed 105/105 with the stage2-v2 interpreter and
strict non-live guard. Staged Git blobs matched the tested working bytes.
The first test attempt failed before collection because a Windows sandbox
temp path was denied. A second attempt failed before collection due to
pytest resolving the parent repo's conftest. The successful invocation used
workspace-local temp and `--confcutdir` at this worktree. Neither early
failure reached OpenCode or a provider.

This file must not be copied into the active receiver as a shortcut.
OpenCode merges config sources, and installed 1.18.11 effective config,
agent permission semantics, provider credential reference, exact endpoint,
egress enforcement, auxiliary-call accounting, protected issuer, and
one-shot live authorization remain unqualified. The free model is limited
to synthetic/public trial content under the provider's current terms.
No real receiver/model, Docker mutation, credential transfer, GPU,
ComfyUI, or production action occurred. Production remains HOLD.
