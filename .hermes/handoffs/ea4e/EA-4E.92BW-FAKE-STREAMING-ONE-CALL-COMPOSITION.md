# EA-4E.92BW Fake Streaming One-Call Composition

Non-live continuation from EA92BV at
`d89b46af2026749012ec6dcfe709bbb7681c050e`. This checkpoint composes
existing acceptance-only durable claim and fake capture accounting with the
pure SSE inspector. It is not a v2 production gate or a receiver probe.

## Source boundary

`tools/ea4e92bw_fake_streaming_qualification.py` adds a separate
HTTP-shaped handler. It validates an injected POST to the chat-completions
route, an exact selected model, a list of messages and `stream: true`
before invoking the existing `QualificationProviderGate`. The scope's raw
request SHA-256, task/run identity, time window, cancellation and revocation
checks remain with that gate. Its durable claim happens before calling the
injected response callback and cannot be refunded. The existing
`AccountedFakeProviderGate` records entered/completed/failed events and
exclusively saves raw response bytes and their hash. The callback's SSE
metadata and chunks are checked by the EA92BV pure inspector before a
capture can complete.

Pre-claim request denials do not consume the fixture budget or call the
response callback. Once claimed, malformed/truncated SSE, non-200/redirect
responses, callback errors, ledger failures, and crashes remain consumed.
Replay and a second handler call are denied. Internal behavior of an
arbitrary injected callback is not observable beyond the single boundary
invocation; this does not attest that an installed receiver or transport
cannot make auxiliary calls.

## Verification

`py -3.14 -m pytest -q -p no:cacheprovider` on the EA92BW dedicated test:
28 passed. The focused EA92C/D/F/J/BV/BW admission, accounting, v1 HTTP,
binding, SSE and streaming-composition ladder: 224 passed, zero failures.
Tests use injected bytes and temporary fake stores; no listener, OpenCode
receiver, provider/model endpoint, GPU or ComfyUI was invoked. Static scan
of the new handler and pure inspector found no process, network or GPU
invocation capability. Codex-bundled Python has no pytest; installed Python
3.14 was used. No full Hermes Core or installed-binary qualification is
claimed.

## Still required

V2 schema, target binding, exact SDK-to-installed-binary provenance,
suppression or accounted denial of title/auxiliary calls, receiver-to-gate
and gate-to-upstream egress, runtime deadlines, trusted capture issuer,
EA92S exact mapped-byte proof, and the EA92K downstream ID roll remain
unclosed. The fake handler does not create live authority, a listener, or
deployment policy. A second real request must not be attempted under this
checkpoint.

`V1=FROZEN_UNCHANGED`, `FAKE_STREAMING_COMPOSITION=PASS`,
`V2_PRODUCTION_GATE=NOT_IMPLEMENTED`, `V2_SCHEMA=NOT_FROZEN`,
`INSTALLED_RECEIVER_PROOF=HOLD`, `TRUSTED_CAPTURE_ISSUER=HOLD`,
`EA92S_EXACT_MAPPED_BYTE=REJECT`, `PRODUCTION_READINESS=HOLD`.
