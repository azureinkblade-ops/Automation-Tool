# EA-4E.92GA Start Witness Authority Status

Status: NON-LIVE READ-TIME AUTHORITY GUARD / TERMINAL HOST HOLD
Baseline: `2bc6e7e3c5eb684a0997799ada140eb97aaa0989`
Date: 2026-10-09 (America/Phoenix)

The read-only durable start witness now rejects an already cancelled
delegation or revoked capability lease before returning a bound STARTED
artifact. Isolated real-SQLite tests cover both transitions; the bounded
fake-only start/delegation ladder passed 203 tests and 26 subtests.

This read-time status check is not an atomic cross-store terminal decision.
The 92FV result-store transaction separately denies a new `SUCCEEDED` result
if cancellation or revocation committed before the final write. Trusted
lease expiry, uncertain-start recovery, terminal evidence verification, and
production host wiring remain open. No real agent or model was invoked.

`INACTIVE_AUTHORITY_START_WITNESS=DENY`
`FINAL_SUCCESS_STATUS_GUARD=92FV`
`LIVE_THREE_AGENT_CONNECTION=NO`
`PRODUCTION_READY=NO`
