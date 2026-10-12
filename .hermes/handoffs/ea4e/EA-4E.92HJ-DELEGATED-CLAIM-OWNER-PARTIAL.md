# EA-4E.92HJ Delegated Claim Owner Partial Implementation

Status: NON-LIVE / FAKE-ONLY / PARTIAL. Parent: EA-4E.92HI.

`AgentDelegatedClaimOwner` is an unwired module. It requires an existing
92HF bridge, derives the 92HH request, runs 92HG preflight, and pins the
accepted attempt to one durable invocation-authorization store instance ID
in the delegation database before calling the general issuer. It checks
the lease against its own clock, not only collaborator clocks. An alternate
authorization store cannot issue or claim for the same attempt.

For a supplied issued authorization, the owner checks the exact durable
issue request and calls `claim_for_execution` with the reserved execution
request ID explicitly set. Only after a successful durable consumption does
it claim the one-shot delegated receiver-start fence. Its `FENCED` result
means *no receiver has been started*. If the authorization was consumed but
the fence is absent or uncertain, replay is UNKNOWN and cannot claim again.
Cancellation/revocation before claim denies without consumption; cancellation
between authorization claim and fence produces UNKNOWN. The two stores are
not atomic and the owner grants no process or model invocation capability.

Focused fake-only tests: 10 passed, 0 failed. The tests cover Kilo and
OpenCode identities, exact replay, reopened authorization store, changed
TTL, alternate store, cancellation/revocation, swapped authorization,
stale collaborator clocks, and faults after consumption. No real receiver,
model, network, Docker, GPU, ComfyUI, or production activation.
The broader delegated/issuer/provisioner ladder passed 154 tests, 0 failed.

This is not the complete 92HI acceptance: independent concurrent callers,
faults at every commit edge, expiry at all boundaries, production trigger
ownership, actual process identity/terminal bytes, and durable result return
remain to be qualified. No app route/startup/scheduler wiring was added.
`PRODUCTION_READY=NO`.
