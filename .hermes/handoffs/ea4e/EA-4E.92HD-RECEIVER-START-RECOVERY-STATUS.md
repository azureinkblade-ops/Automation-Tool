# EA-4E.92HD Receiver Start Recovery Status

Status: NON-LIVE / FAKE-ONLY. Parent: EA-4E.92HC.

The explicit, default-disabled `AgentPingRecoveryHost` now accepts an optional
`SQLiteAgentReceiverStartFenceStore` bound to the same authority and start
stores. For Kilo/OpenCode only, `inspect(attempt_id)` reports
`RECEIVER_START_UNKNOWN` when a durable one-shot start claim exists but no
terminal capture is available. This remains visible after delegation
cancellation or lease revocation. A valid terminal capture takes precedence
while authority is active; an existing verified result and originator message
retain their existing `MESSAGE_AVAILABLE` state.

The internal app configurator passes this optional dependency through. There
is no startup hook, HTTP route, scheduler, adapter call, process start, result
return, or model call. Existing callers without the fence retain their prior
behavior. A claim proves only that a start was reserved, not that a process
started or produced bytes. `RECEIVER_START_UNKNOWN` is a stop-and-reconcile
state, never an authorization to retry.

Fake-only focused ladder: 49 passed, 0 failed, with one inherited `app.py`
invalid-escape deprecation warning. The first test attempt did not execute
tests because this sandbox denied pytest's default temporary directory; the
rerun used a fresh worktree-local temporary path and passed. No real Codex,
Kilo, OpenCode, model, Docker, GPU, ComfyUI, or production activation was
invoked. `PRODUCTION_READY=NO`.

Next boundary: implement and qualify a trusted receiver-process owner that
binds exact invocation authorization, process identity, terminal bytes, and
durable capture to the accepted attempt. Neither the fake start fence nor
this read-only status substitutes for that proof.
