# EA-4E.92CQ Kilo local-token handoff design

Status: NON-LIVE DESIGN / PRODUCTION TOKEN HANDOFF HOLD
Baseline: `4bdaf6262cc52af8c6f34e5e081d9bc0b8eebef7`

## Separation of credentials

The current `production_credential_preflight.py` checks the sealed Kilo
free-model route against a local `kilo.db` reference and its existing
transport/model IDs. That preflight must remain unchanged. A future
custom-provider gateway is a new route with a different credential policy;
the 92CM inert probe did not qualify the old auth database for it.

For the candidate gateway route, Hermes Authority would authorize an exact
execution attempt. A gateway owner would provision a one-request durable
budget and a fresh, high-entropy, attempt-bound **local** token after that
authorization is verified. The upstream provider credential would remain
in a separate gateway-only store and would never enter Kilo's argv, config,
environment, repository, or audit records. Kilo would receive only the
local token and the attempt-specific loopback endpoint. The gateway would
store only a verifier for that token, compare it in constant time, check
attempt/binding/expiry/revocation, then atomically claim the durable send
budget before any upstream connection. Failure after claim never refunds
or automatically retries.

The 92CM dummy probe showed Kilo accepts a `KILO_CONFIG_CONTENT` environment
value with an OpenAI-compatible `apiKey` and `baseURL`. For a future local
token, that is the smallest candidate handoff: construct the config in
launcher memory, supply it to one isolated child, never print or persist
the config or token, and terminate the child and gateway together. This is
**not yet an approved production delivery mechanism**. The child retains
its environment for its lifetime, and a same-user process may be able to
inspect it. A loopback TCP bearer token also does not by itself prove the
request came from the intended Kilo PID. A per-attempt port and one-use
budget reduce exposure but do not close that peer-identity gap.

## Lifecycle and evidence contract

- Provision only after exact authorization and gateway/receiver binding;
  no token in governance documents, Git, or command-line arguments.
- Local token is fresh for one attempt, expires no later than the attempt,
  and is invalidated on cancellation, revocation, teardown, or crash.
- Gateway rejects wrong token, wrong route/model, duplicate/concurrent
  calls, expired or revoked attempts, and any send after durable claim.
- The durable budget survives process restart; a failed or uncertain send
  remains consumed. Another attempt needs a new authorization and token.
- Audit only IDs, timestamps, claim outcome, request/response sizes and
  digests, and sanitized status. Never audit token, upstream credential,
  prompt text, raw headers, or raw response.

## Gates before implementation or live use

1. Decide and document the local adversary model. Either qualify a reliable
   Kilo-peer identity boundary for loopback requests or explicitly accept
   same-user process access as trusted. No such decision is made here.
2. Specify a private upstream credential store and who can read/rotate it.
   The existing Kilo `kilo.db` readiness check is not that store.
3. Freeze new custom-route transport/model/credential IDs and a config
   identity. Do not reuse the existing free-route sealed IDs.
4. Fake-test token issuance/verification, expiry, revocation, replay,
   concurrent requests, crash/restart, config redaction, and teardown.
5. Qualify a production-capable gateway and its egress restrictions with
   fake upstream transport before seeking an exact one-request live pilot.

This checkpoint creates no token, reads no credential, starts no receiver,
opens no listener, changes no production code, and authorizes no real
provider/model call. The 92CM probe claim remains consumed. EA-4E.92S
exact mapped-byte proof remains REJECT/HOLD independently.
