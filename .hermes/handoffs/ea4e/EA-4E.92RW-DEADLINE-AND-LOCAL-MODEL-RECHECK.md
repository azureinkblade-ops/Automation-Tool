# EA-4E.92RW Deadline And Local Model Recheck

Status: NON-LIVE CORRECTION / NATIVE AND MODEL GATES HOLD.
Date: 2026-10-26.
Predecessor: `e64226a` (92RV).

The successor checks its remaining deadline while traversing the staged
inventory and starts the Docker CLI timeout before writing stdin. The write
is handled on a bounded thread, so a stalled input pipe no longer prevents
the controlling thread from killing the CLI. Focused strict non-live fake
tests passed 27/27. This improves the bound but does not establish an
absolute 120-second wall across OS process creation and cleanup. No native
probe or model run occurred.

Official Ollama v0.40.11 `GenerateHandler` source checks the resolved local
model and returns 404 when it is absent; it does not call the CLI
`showOrPullModel` path. A `:cloud` reference or remote-model config follows a
different branch. The candidate hardcodes `qwen3:14b`, whose pinned manifest
has a GGUF model layer and whose pinned config is local GGUF without remote
host/model fields. This is source and artifact evidence, not proof of the
container binary's provenance or runtime behavior. The non-model Bash
transport is still unverified in the image. The model, GPU, receiver, and
agent handoff remain prohibited without new exact authorization.

Source: https://github.com/ollama/ollama/blob/v0.40.11/server/routes.go#L285-L353
