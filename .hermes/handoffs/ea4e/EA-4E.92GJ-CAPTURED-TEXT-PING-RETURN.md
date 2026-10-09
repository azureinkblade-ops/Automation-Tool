# EA-4E.92GJ Captured Text Ping Return

Status: NON-LIVE RESULT RETURN / PRODUCTION HOST HOLD
Baseline: `ff73a8792a96db28882a0228e92ed88c84acedb1`
Date: 2026-10-09 (America/Phoenix)

`return_captured_text_ping()` joins the durable accepted task/lease/receipt,
STARTED witness, and immutable Kilo/OpenCode terminal capture into the
committed no-output ping schema. It then uses the existing atomic result and
originator-mailbox writer. For this ping schema, the writer now derives an
unsupplied delivery timestamp from its trusted transaction clock; callers
cannot use an old/future timestamp to assert lease validity. The result
store's transaction still rechecks cancellation/revocation and lease time.

On restart, an existing durable result is replayed first, including after
later cancellation or expiry; no capture re-read or second send is needed.
If no result exists, missing capture remains UNKNOWN and produces no result
or mailbox message. A cancellation between capture and new-result write
denies success. Exact result replay retains one originator message.

Fake-only tests use isolated real SQLite stores for Kilo and OpenCode,
including start-store reopening, missing capture, cancellation before new
success, and cancellation after a durable success. Focused tests passed 5;
the bounded cross-agent/start/result ladder passed 251 tests and 26
subtests with zero failures.

This function never invokes a receiver. The production app and trusted
adapter host do not yet call it, and Codex's separate durable structured
terminal path is not routed through it. Generic output-byte verification
and live receiver qualification remain open. No real receiver/model,
network, Docker mutation, GPU, ComfyUI, or production activation was used.

`KILO_OPENCODE_CAPTURED_PING_RETURN=PASS_FAKE_ONLY`
`ORIGINATOR_MAILBOX_ONCE=PASS_FAKE_ONLY`
`PRODUCTION_RESULT_HOST_WIRED=NO`
`LIVE_THREE_AGENT_CONNECTION=NO`
`PRODUCTION_READY=NO`
