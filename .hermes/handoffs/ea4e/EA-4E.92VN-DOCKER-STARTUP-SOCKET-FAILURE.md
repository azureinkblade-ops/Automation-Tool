# EA-4E.92VN Docker startup socket failure

Date: 2026-10-30 (America/Phoenix)
Status: STARTUP FAILURE CLASSIFIED / NATIVE BUILD HOLD / PRODUCTION HOLD

Read-only local diagnostics identified the cause behind the failed Docker
health checks. The Desktop UI opened a backend-error dialog, but no visible
window was available. The backend log reports that Inference-manager startup
cannot remove a pre-existing `Docker/run/dockerInference` endpoint and then
stops the engine. The endpoint and two neighboring runtime entries are
zero-byte reparse points dated before the failed launch. No model files were
found in the runtime directory's top-level inventory. This does not prove
that a repair will succeed or that no later startup fault exists.

No Docker runtime file was moved or deleted, no process was stopped, and no
container, build, model, GPU assignment, receiver, agent handoff, or
production activation ran. A separately governed one-attempt recovery was
proposed for exact approval. Native build and production remain HOLD.
