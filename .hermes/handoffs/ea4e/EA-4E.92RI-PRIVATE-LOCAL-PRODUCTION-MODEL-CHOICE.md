# EA-4E.92RI Private Local Production Model Choice

Status: OPERATOR MODEL CLASS CHOSEN / NON-LIVE / PRODUCTION HOLD.
Source baseline: `d93938ad15ffea80ed892d8ba5ecbe205e3e3445`.

David selected a private local model for production agent handoffs. The
existing isolated OpenCode `config/config.json` selects `ollama/qwen3:14b`
for the default and EA-4E receiver agent, defines only the local Ollama
provider at `http://localhost:11434/v1`, and has SHA-256
`bf98deaa2a8c052213a599716c5fa2d229bb89b72d7cb810e7b6a4cc178b7756`.
This is the current local candidate, not an independently approved final
model pin or evidence that Ollama is running or contained.

The separate Nemotron 3 Ultra Free config and command remain inert
synthetic/public trial candidates. They were not installed. The free
endpoint must not receive private repository content, notes, credentials,
or ordinary agent delegations. No private handoff may silently fall back
to that endpoint.

Before a real local-model qualification, pin the exact model artifact and
runtime, prove effective OpenCode config and provider routing, enforce
receiver egress and call accounting, qualify the protected one-use issuer,
and obtain an exact bounded authorization for any receiver/model/GPU call.
The current `home/.opencode/config.json` is also present (SHA-256
`98e31c27edb2aceb91a310a742e25d188cc50ca840fea056cc169fe50e88a649`);
its merge with `config/config.json` is not established by these file hashes.

No receiver, model, GPU, ComfyUI, Docker mutation, credential transfer, or
production activation occurred. Strict 92AT remains REJECT/HOLD and the
separate local-container profile remains unqualified. Production is HOLD.
