# EA-4E.92GF Ping Result Transaction Time Guard

Status: NON-LIVE IMPLEMENTED / PRODUCTION RESULT HOST HOLD
Baseline: `058530bf29f33e44b5fa8812b43b485e2b1d11d4`
Date: 2026-10-09 (America/Phoenix)

For `hermes.agent_ping_result/v1` new SUCCEEDED writes only,
`SQLiteDelegationResultStore` now obtains a timezone-aware UTC clock value
inside its existing result/mailbox transaction. It denies a new success
before `lease.not_before`, at or after `lease.expires_at`, before the
result's completion time, or when caller-supplied `delivered_at` differs
from the trusted transaction second. A naive/invalid clock denies. The
clock is injectable for isolated fake-only tests; the production default
reads system UTC. Exact durable replay still returns the prior result and
mailbox identity without a new time check or send. Non-ping result schemas
retain their existing behavior; this slice does not claim generic
file-output verification.

Red tests first demonstrated the absent clock injection. Focused result
tests then passed 37 tests and 6 subtests. The bounded cross-agent/start/
result/mailbox ladder passed 235 tests and 26 subtests after the final
clock/delivery denial cases, with zero failures.

The result store still does not prove that a real receiver ran. The
production host must read the durable adapter terminal record, bind it to
the STARTED witness, and recover across stores without a second send.
Only the no-output ping schema has this transaction-time success guard.
No real receiver/model, Docker, network, GPU, ComfyUI, or production
activation was used.

`PING_NEW_SUCCESS_TRUSTED_TIME=PASS_FAKE_ONLY`
`PING_EXACT_REPLAY_AFTER_EXPIRY=PASS_FAKE_ONLY`
`PRODUCTION_RESULT_HOST_WIRED=NO`
`PRODUCTION_READY=NO`
