# EA-4E.92BQ Capture Issuer And Provider Trust Boundary

Read-only, non-live decision record at
`cac3b91972f135a276dbddbbdea01137fae8e045`. No authority was issued,
no process/model/provider was invoked, and no runtime or test source changed.

## Verified source facts

`ProductionOperatorIdentityVerifier.verify()` in
`production_activation_authorization_ceremony.py` only compares the supplied
operator ID to a configured string. `production_app_config.py` defaults that
string to `hermes-local-operator`. This is an identity label, not evidence
that an independent operator approved a particular capture issue request.
The production activation ceremony and authorization must not be reused as
capture authority.

`ea4e92c_provider_call_control.py` labels its provider gate
acceptance-owned/networkless. Its scope is fixture-provisioned into the
production-shaped durable store with `qualification-only` scope; it cannot
observe or constrain the installed OpenCode binary's internal model calls.
EA92N found that the available OpenCode 1.18.11 source uses AI SDK streaming
paths that may conflict with EA92I v1's non-streaming provider contract.
Source-to-installed-binary provenance and the actual effective request remain
unproven. The current capture store in EA92BP stores supplied bytes and
consumes one *process-start* credit; it is neither an issuer nor a provider
call ledger.

## Decision for subsequent non-live qualification

Treat capture issuance as a separate trust domain. A production candidate
requires a trusted issuer/broker principal distinct from the receiver, with
an operator approval event bound to the exact EA92BN artifact hash, issue
request hash, source commit, run, model/config/executable identities, expiry,
and one-start budget. The capture runtime verifies a pinned issuer identity
and receipt before `persist_issued`; the receiver cannot issue, rewrite,
claim, or read issuer secrets. Merely running issuer and receiver under the
same Windows account, comparing an operator string, or signing with a key
available to that account would not establish this boundary. An OS principal,
key custody, ACL, and approval mechanism must be independently qualified and
bound to exact deployment artifacts before a real issue path exists.

Separately, a provider gate must enforce at most one upstream call *inside*
the CLI session. It must own a durable no-refund reservation, deny retries,
fallback, redirects and direct receiver egress, and record request/response
identity. Receiver process count is not a substitute. First qualify the
installed SDK's effective request shape and streaming behavior through an
inert fake transport with process/network tripwires. If it requires streaming,
EA92I v1 stays unchanged until a separately reviewed contract revision or
compatible execution path is accepted; do not silently modify the request.
CPU-only behavior is also unproven and must be observed or enforceable, not
inferred from the model name.

## Next bounded work and stop line

1. Non-live deployment review: identify a real, distinct issuer principal,
   approval source, key/ACL custody, and pinned verification material. Show
   the receiver cannot access issuer capability. Do not provision a key or
   install a service as part of this review.
2. Non-live SDK qualification: bind source/package evidence to the installed
   binary and capture the effective provider request against a fake transport.
   No real receiver/model/provider call is allowed by this document.
3. Only after both are proven, implement capture-specific receipt verification
   and provider reservation, with isolated fake tests, staged/committed-tree
   gates, and complete dependency closure. Then request a separate exact
   one-shot live packet.

Current result: `TRUSTED_CAPTURE_ISSUER=UNBOUND`,
`PROVIDER_ONE_CALL_ENFORCEMENT=UNPROVEN`, `EA92I_SDK_COMPATIBILITY=HOLD`,
`EA92S_EXACT_MAPPED_BYTE=REJECT_ON_AVAILABLE_EVIDENCE`,
`PRODUCTION_READINESS=HOLD`. EA4 historical capture remains missing;
EA92A fresh capture has not happened. This is a stop line, not permission to
create live authority from the fake tests.
