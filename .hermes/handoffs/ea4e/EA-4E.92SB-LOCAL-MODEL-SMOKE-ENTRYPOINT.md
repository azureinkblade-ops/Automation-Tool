# EA-4E.92SB Local Model Smoke Entrypoint

Status: NON-LIVE ENTRYPOINT CANDIDATE / REVIEW AND MODEL AUTHORIZATION HOLD.
Date: 2026-10-26.
Predecessor: 92SA approved non-model Bash transport success.

The one-shot model-smoke entrypoint fixes the previously reviewed Ollama
image digest, staged `qwen3:14b` model root, Docker CLI identity, and private
local Docker host. It creates a fresh ceremony UUID and calls the reviewed
`run_smoke` path once. There are no user-supplied model, endpoint, prompt,
container, or resource arguments. The exact staged model inventory was
rehashed and validated read-only before this candidate was committed.

The focused strict non-live entrypoint and smoke-contract suite passed
28/28 fake tests. This does not qualify model loading or inference. The
entrypoint and imported launcher require independent read-only review at a
pinned commit, followed by a separate exact one-shot authorization before
any native model/GPU use. The 92SA non-model authorization is consumed and
cannot be reused. No model, receiver, or agent handoff ran. Production
remains HOLD.
