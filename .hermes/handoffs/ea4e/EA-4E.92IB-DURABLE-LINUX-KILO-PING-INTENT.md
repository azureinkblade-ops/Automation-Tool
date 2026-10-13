# EA-4E.92IB Durable Linux Kilo Ping Intent

Status: NON-LIVE / SQLITE PLAN RESERVATION / PRODUCTION_READY=NO.

`SQLiteAgentLocalKiloPingIntentStore` reserves the full 92IA plan once per
accepted attempt in the authority SQLite database. Reservation verifies the
accepted start witness and bridge, the complete rebuilt plan, current
delegation/lease/receipt/bridge rows, and the lease window while holding a
write transaction. It denies prior authorization claim, receiver-start
fence, terminal capture, result, or Windows text-process intent. The Windows
intent writer symmetrically denies a prior Linux plan reservation. A fresh
store instance can read and reverify the reservation, but cannot reserve
again. A reserved plan remains non-launchable.

Focused tests: 25 passed, 0 failed. Affected fake-only ladder: 222 passed,
0 failed. Tests cover durable replay, changed plan, cancellation, both
cross-runtime directions, tampered row, claimed start, lease expiry, and
independent competing writers. No Docker object, Kilo/OpenCode process,
model, credential, GPU, ComfyUI, or production activation was invoked.

This is not a launch permit or trusted process observation. Next, a concrete
container owner must bind the same plan and accepted authority to exact
image/config/peer identities, one process-start decision, bounded raw-byte
capture, and confirmed containment. The real provider/model and credential
scope need separate qualification and exact bounded live authorization.

## Preclaim revalidation correction

Before a future container owner can consume a reserved plan, `verify_plan()`
must also recheck the lease window and absence of a claim, start fence, terminal
capture, result, or conflicting Windows intent under the same SQLite write
lock. The original 92IB reservation checked these only at reservation time.
The corrected verifier denies a plan after lease expiry or a subsequent start
fence while retaining the row for audit. Focused tests: 27 passed. Nearby
handoff/claim regression: 116 passed. This does not authorize a container
create/start or qualify a real receiver/model.
