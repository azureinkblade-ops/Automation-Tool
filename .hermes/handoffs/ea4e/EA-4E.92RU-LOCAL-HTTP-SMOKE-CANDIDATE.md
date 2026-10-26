# EA-4E.92RU Local HTTP Smoke Candidate

Status: NON-LIVE CANDIDATE / INDEPENDENT REVIEW AND NATIVE GATES HOLD.
Date: 2026-10-26.
Predecessor: `9e32615` (92RT), independent review HOLD.

The 92RT review found that `ollama run` could attempt a missing-model pull,
and that Docker inspect JSON accepted duplicate keys. The successor rejects
duplicate keys in inspect output and uses the local Ollama HTTP API instead
of the CLI run handler. It queries `/api/tags` before inference and requires
the pinned `qwen3:14b` manifest digest. Only then does it send one synthetic
`POST /api/generate` with a short generation bound. The HTTP transport is
hardcoded to `127.0.0.1:11434` inside a `--network none` container; it has
no route to a remote model. The existing exact-container cleanup remains.

Focused strict non-live fake tests passed 23/23. These tests do not establish
that `/bin/bash` and its `/dev/tcp` feature exist in the pinned image, that
the staged model loads, or that the HTTP response succeeds. No container,
model, GPU, receiver, or agent handoff ran for this checkpoint. A fresh
independent read-only review and a separately approved non-model native
transport probe are required before any model-smoke authorization. Production
remains HOLD.
