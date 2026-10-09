# EA-4E.92FM Request-Bound Send Claim Design

Status: NON-LIVE DESIGN / RELEASE AND RECEIVER HOLD
Baseline: `016e58b1f03464ff9a4e88a4d2c03dd364598be4`
Date: 2026-10-08 (America/Phoenix)

92FL defines an authenticated pending frame and a release frame that names a
`claim_receipt_hash`. The existing 92DW gateway uses
`DurableInvocationAuthorizationStore.claim()`, which atomically consumes an
invocation authorization but returns only allowed/reason/consumed. Its durable
row does not bind the accepted request nonce, raw-body digest, peer container,
or source commit. Therefore neither its return value nor a caller-computed
hash is a request-bound release receipt. No release may be wired on that
basis.

## Proposed host-owned claim

Add a separate append-only, rollback-detecting gateway-send store. One row
identifies a single run, delegation, ExecutionAttempt, invocation
authorization, exact network/gateway/receiver IDs, accepted peer address,
request nonce, body length/digest, source commit, and UTC claim time. It
retains no raw body, prompt, child token, upstream credential, or response.
The store enforces unique invocation-authorization/attempt and run/nonce
identities. The receipt hash is the SHA-256 of a versioned canonical row
preimage, returned only after its transaction and external rollback anchor
are durable. This receipt is an audit binding, not independent authorization.

Hermes must validate authority, cancellation/revocation, strict body shape,
child token, and fresh peer evidence before the existing invocation claim.
Inside the existing claim's validate callback it rechecks those mutable
conditions. It then commits the invocation claim first and the new
request-bound send claim second. Only after **both** stores confirm durable
consumption and the recorded receipt matches the 92FL pending frame may
Hermes send one authenticated release frame. The gateway cannot access or
mint either store. A failure after the first claim leaves that authorization
consumed and the request unanswered; it never refunds a budget or attempts an
automatic resend. The new store does not replace existing invocation
authorization and does not create a second issuer.

## Crash and denial matrix

| Point | Required outcome |
| --- | --- |
| Before either claim | Deny this request; no release; no implicit retry. |
| Invocation consumed, bound claim absent | Deny; invocation remains consumed. |
| Both claims durable, release not sent | Deny/uncertain; both remain consumed. |
| Release sent, acknowledgment lost | Outcome uncertain; no second release or refund. |
| Duplicate nonce, changed body, or competing request | Deny without replacing either row. |
| Store/anchor mismatch or unreadable state | Hold; no release or reconstruction from logs. |
| Gateway or receiver crash | Exact-ID cleanup and durable reconciliation; no replay. |

The first implementation slice should be pure receipt material validation
and fake-store tests, then an isolated temp-SQLite store with crash/race and
rollback cases. The production gateway, Docker exec control transport, Kilo
receiver, model, and activation remain separate gates. Do not alter the
existing 92CN exact-body-hash fixture or call a fake response merely because
92FL frame HMAC validates.

## First source-only slice (2026-10-08)

`tools/hermes_core/kilo_send_claim.py` validates exact versioned candidate
material and compares its run/nonce/commit/container/peer/body fields with a
pending header. It exposes a candidate hash only; it neither writes a store
nor returns a release receipt. `tests/hermes_core/test_ea4e92fm_kilo_send_claim.py`
covers canonical ordering, malformed identities/timestamps, and mismatched
pending material. The affected pure-frame/fake-gateway ladder passed 58/58.
The separately proposed durable send-claim store remains unimplemented.

`REQUEST_BOUND_DURABLE_RECEIPT=NO`
`INVOCATION_CLAIM_ALREADY_DURABLE=YES`
`CONTROL_RELEASE_AUTHORIZED=NO`
`RECEIVER_EXECUTED=NO`
`PRODUCTION_READY=NO`
