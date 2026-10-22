# EA-4E.92RE Nemotron Trial Model Selection

Status: OPERATOR MODEL CHOICE RECORDED / NON-LIVE / PRODUCTION HOLD.
Source baseline: `da137a1f4ec539cb0dd30ee7f8c935c5982007fd`.
Decision date: 2026-10-22 (America/Phoenix).

The operator selected **Nemotron 3 Ultra Free** for the first governed
OpenCode model handoff. The attached interactive OpenCode screenshot shows
that selection, but its on-screen checkpoint text is not an instruction,
and the screenshot does not attest EA-4E's isolated login, config, endpoint,
call count, or response. This is a model choice, not a live-call grant.

Current OpenCode documentation lists model ID `nemotron-3-ultra-free` at
`https://opencode.ai/inference/openai/v1/chat/completions`. It says the
NVIDIA free endpoint is trial-only, must not receive personal or confidential
data, and logs use for security and product improvement. Therefore the first
EA-4E qualification may use only an inert synthetic/public task. Real agent
delegations containing repository content, credentials, private notes, or
user data remain outside this choice. Source:
https://opencode.ai/v2/docs/console/models/

Read-only local inspection found that EA-4E's isolated
`config/config.json` still has SHA-256
`bf98deaa2a8c052213a599716c5fa2d229bb89b72d7cb810e7b6a4cc178b7756`,
selects `ollama/qwen3:14b` at top and receiver-agent level, and defines
only the `ollama` provider. Neither it nor the installed receiver was
changed. The existing 92GS canonical binding and 92GQ capture entry have
a fake-only Nemotron trial path, but no trusted model-binding verifier,
usable isolated credential, enforced egress/call accounting, or real
receiver containment has been qualified.

Next non-live gate: prepare and independently review a versioned isolated
OpenCode config candidate and actual installed-binary merged-config
semantics, exact endpoint and streaming transport, credential reference,
egress policy, and synthetic task bytes. Do not copy interactive credentials
or infer isolation from `OPENCODE_CONFIG_DIR`: official documentation says
config sources merge rather than replace each other. Source:
https://opencode.ai/docs/config/

The protected one-use issuer, bounded live-call packet, and production
decision remain separate. No receiver, model, credential transfer, Docker
mutation, GPU, ComfyUI, or production action occurred in this checkpoint.
Strict 92AT remains REJECT/HOLD; the accepted 92DE local profile is not yet
qualified.
