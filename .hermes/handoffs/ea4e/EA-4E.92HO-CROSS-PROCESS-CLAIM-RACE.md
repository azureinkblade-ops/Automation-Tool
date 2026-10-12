# EA-4E.92HO Cross-Process Claim Race Qualification

Status: NON-LIVE / FAKE-ONLY / PARTIAL. Parent: EA-4E.92HM.

Two independent Windows-spawned processes raced for the same accepted
OpenCode attempt using separate SQLite connections. The first diagnostic
run exposed a status-classification race: the loser could pass the initial
intent/fence checks, then encounter the winner's committed fence during
preflight and report DENIED. No second authorization or fence was created,
but an already-claimed start is an uncertain/reconcile-only state.

The claim owner now rechecks durable intent/fence state when preflight raises
an integrity error. A preexisting claim, or failure to inspect its state,
returns UNKNOWN; an error with no observed claim remains DENIED. The race
test asserts one FENCED and one UNKNOWN outcome, one consumed authorization,
and one fence. Two separate 20-iteration stress runs passed after the fix.
The committed regression test retains five independent process races. The
affected delegated/issuer/fence/provisioner ladder passed 164 tests, 0
failed before commit.

This is not a real receiver-process start or terminal observation. It does
not establish trusted process provenance, capture bytes, or result return.
No real receiver/model, network, Docker, GPU, ComfyUI, or production
activation was invoked. `PRODUCTION_READY=NO`.
