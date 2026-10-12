# EA-4E.92HC Delegated Receiver Start Fence

Status: NON-LIVE / FAKE-ONLY. Parent: EA-4E.92HB.

The generic worker STARTED record does not limit the later Kilo/OpenCode
receiver process. `SQLiteAgentReceiverStartFenceStore` adds a separate,
versioned one-shot claim per accepted attempt in the authority SQLite DB.
It binds the receipt, launch, STARTED result, receiver, idempotency key, and
runtime run ID. A second caller always denies; `get` exposes historical
ambiguity after restart or cancellation but never grants another start.
Cancellation/revocation and the lease time window are checked before the
first claim and rechecked in the write transaction. Two independent claimers
produce exactly one durable row in the fake concurrency test. The trusted
clock is sampled only after SQLite's write lock is acquired; a lock-delayed
claim at the lease-expiry boundary is denied.
An existing terminal capture or verified result also denies a late first
claim, closing the upgrade/replay case where an attempt predates this fence.

The fence does not call an adapter, start a process, inspect output, grant
invocation authorization, or prove receiver-process provenance. A claim can
survive a crash before any process starts, so the later owner must reconcile
it as UNKNOWN rather than retry. The owner must separately verify exact
invocation authorization and runtime/credential binding immediately before
the single process start; no such owner is wired here.

Focused fake-only authority/start/capture/recovery ladder: 50 passed,
0 failed, with one inherited `app.py` invalid-escape warning. No real
Codex, Kilo, OpenCode, model, Docker, GPU, ComfyUI, or production activation
was invoked. `PRODUCTION_READY=NO`.
