# EA-4E.92BT Streaming Contract Impact Review

Non-live design review at `7b4bbe992c3aa8006d7ae67faed833389b175ff9`.
No v1 source, test, registry, sealed ID, runtime, or deployment artifact is
changed by this review. No receiver, model, provider, GPU, or production
activation is authorized.

## Decision basis

EA92BS tested the OpenCode-scoped `@ai-sdk/openai-compatible` 2.0.41 and `ai`
6.0.168 packages against an injected, networkless transport. `streamText()`
sent `stream: true`; `generateText()` did not. A synthetic 503 produced one
attempt with `maxRetries: 0` and three with `maxRetries: 2`. The local
OpenCode 1.18.11 source's default AI SDK path calls `streamText()`, while its
title-generation path passes `retries: 2`. These are SDK/source findings,
not installed-binary or whole-session observations.

EA92I/J freeze `hermes.opencode-provider-binding/v1` with
`provider.stream_allowed=false`, `network_retry_limit=0`, and
`max_provider_calls=1`. EA92F's offline handler rejects `stream: true`
before consuming its fake budget. Changing the boolean in v1 is invalid by
contract and by existing negative tests. No v1 fixture or historical result
may be rewritten to accommodate the SDK.

## Candidate v2, not frozen

The narrow candidate is a distinct, versioned OpenCode provider binding and
gate contract whose selected response mode is SSE. It must not mean unlimited
streaming or unlimited model calls. A single admitted HTTP POST may carry a
bounded SSE response; each POST attempt, including a retry or redirect,
counts as a separate provider-call attempt. The durable one-shot reservation
must be consumed before upstream bytes and never refunded on timeout, abort,
malformed/truncated SSE, crash, or uncertain outcome.

Before v2 can be frozen, independently specify and fake-test:

- Exact request method, route, model, canonical body bytes or reviewed
  effective-body identity, `stream: true`, headers and SDK package identity.
  Reject unknown body mutation and any second request before forwarding.
- No SDK retry/fallback under the selected task path. In particular, prove
  title generation and other auxiliary LLM calls are disabled, isolated from
  this qualification, or deterministically denied without falsely reporting
  a successful one-call capture. A process-start limit is not a call limit.
- Bounded request bytes, response bytes, SSE frame/event count and duration;
  strict content type, UTF-8/framing, terminal marker, malformed/error event,
  truncation and disconnect handling. Retain exact raw bytes and hashes;
  parsed text alone is not replayable transport evidence.
- One atomic durable call reservation, cancellation/revocation check,
  no-refund terminal accounting, restart/crash replay denial, and explicit
  response/audit failure behavior. Existing EA92C/F are acceptance-only and
  do not provide a deployed listener or receiver egress containment.
- An enforced receiver-to-gate-only path and gate-to-approved-upstream-only
  path. Loopback URL fields and injected fake fetch do not prove bypass
  prevention. CPU-only model behavior remains separately unproven.

Do not preselect a v2 schema ID, field set, policy digest or model binding ID
from this document. Those are implementation and target-freeze decisions
requiring exact SDK-to-installed-binary provenance or a separately authorized
one-start inert receiver probe. A compatible non-streaming receiver path may
be proposed instead, but it needs the same provenance and one-call proof.

## Downstream closure

EA92K records 13 shared core ID derivations affected when OpenCode's
registered model binding changes. The EA6 registry and EA7/8/11/14/17/18/
21/22/26 direct dependencies, plus EA23 cached IDs and EA28/29 downstream
dependencies, must be rederived in topological order from real reviewed
target material. The Kilo pin must not be altered to make those IDs match.
Existing durable records and historical authority remain intact; new
request-scoped authority would be required for a new binding. EA92K is an
impact inventory, not a complete source/deployment/fixture closure.

No current registry value, v1 golden fixture, shared cached constant or
sealed contract is rolled during this review. A future roll needs its own
exact file/hash manifest, staged and committed-tree qualification, no new
failures, and a separate deployment/live authorization.

## Next gate

Implement a separate fake-only SSE gate/response parser only after the v2
semantics and exact bounded test surface are reviewed. Then qualify the
installed receiver's effective request and auxiliary-call behavior through
an independently controlled inert transport under an exact one-start
authorization. If a second call, direct egress, uncontrolled retry, or
unverifiable stream occurs, fail closed and consume any started authority.

`V1=FROZEN_UNCHANGED`, `V2=DESIGN_CANDIDATE_NOT_FROZEN`,
`CURRENT_BINDING_ROLL=NO`, `INSTALLED_RECEIVER_PROOF=HOLD`,
`TRUSTED_CAPTURE_ISSUER=HOLD`, `EA92S_EXACT_MAPPED_BYTE=REJECT`,
`PRODUCTION_READINESS=HOLD`.
