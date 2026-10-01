# EA-4E.92BU Streaming v2 Test-Contract Design

Non-live, review-only continuation of EA92BT at
`f04db59f0e6fe6a90bb0c84400ad1d852e37f94f`. This document defines the
smallest fake-only behavior to qualify before a streaming OpenCode binding
could be frozen. It does not authorize a receiver start, provider/model call,
network listener, production activation, or a change to v1.

## Boundary

The existing `hermes.opencode-provider-binding/v1`, its golden ID and
fixtures, and EA92C/F admission remain unchanged. EA92F is a non-streaming,
acceptance-only HTTP-shaped handler; it is not a listener or an egress
control. A v2 candidate must use a different versioned binding and a
separate fake handler. A boolean flip in v1 is not a migration.

The object under test is one HTTP `POST /v1/chat/completions` with an exact
reviewed request body containing `stream: true`, followed by one bounded SSE
response. A provider call is one upstream request attempt, not one receiver
process or one complete text stream. A retry, redirect, fallback, title
generation, or other auxiliary LLM request is a second call and must be
denied or separately governed. No success claim is valid if it is silently
omitted from the capture.

## Candidate transport contract (not frozen)

These are proposed fake-gate limits, not target deployment values. They may
be changed only by an explicit v2 design review before implementation:

| Property | Candidate rule |
| --- | --- |
| Request | Exact method/route, `application/json`, UTF-8 JSON object, no duplicate keys or nonfinite values, `stream` exactly `true`, selected model and SHA-256 of raw body bound to the task. At most 65,536 body bytes. |
| Provider attempts | One durable claim before any forwarding; maximum one upstream POST; zero redirects, retries, fallback targets, or auxiliary calls under the same authority. A started attempt is never refunded. |
| Response | Status 200 and exactly `text/event-stream` (a reviewed UTF-8 charset suffix may be separately permitted); no content encoding; at most 65,536 raw body bytes and 128 complete events. No event line above 4,096 bytes. |
| Time | At most 30 seconds from first upstream byte to terminal event in fake-clock tests; deadline is checked between chunks, not only after completion. No wall-clock policy is implied for deployment yet. |
| Framing | UTF-8 bytes, `\n` or `\r\n` line endings, complete blank-line-delimited `data:` events. Each nonterminal data payload is one JSON object without duplicate keys or nonfinite constants; terminal payload is exactly `[DONE]` and appears once, last. No trailing non-whitespace bytes. |
| Evidence | Retain exact request and response bytes, their SHA-256 hashes, status/content-type, monotonic byte/event counters, claim and terminal outcome. Parsed text is not a substitute for raw transport evidence. |
| Failure | Oversize, timeout, malformed UTF-8/JSON/framing, upstream error/disconnect, missing or duplicate terminal, durable write failure, or uncertain outcome is fail-closed. Once the claim begins, terminal accounting is no-refund. |

The strict framing rules deliberately do not assume that the installed
OpenCode binary accepts such a response. Exact SDK fixture compatibility and
installed-binary behavior are separate gates. If the pinned SDK needs a
different legal SSE shape, amend this candidate before freezing v2; do not
loosen a deployed parser ad hoc.

## Exact fake-only acceptance surface

The future test suite should use an injected byte-chunk source and fake
clock, with process/network/filesystem tripwires. It must not start a
listener or load the installed receiver. Assertions should cover:

1. One valid request and split-chunk SSE response: one pre-forward durable
   claim, one callback invocation, exact raw-byte/hash evidence, terminal
   success only after `[DONE]` and durable receipt.
2. Boundary sizes: exactly-at-limit success and one-byte/one-event/
   one-line-over-limit denial, including a chunk that crosses a limit.
3. UTF-8 code point, CRLF, and delimiter splits across chunks; malformed
   UTF-8, missing blank line, malformed/duplicate-key JSON, missing,
   duplicate, or nonfinal `[DONE]` denial.
4. Non-200 status, wrong content type, compression, connection drop,
   pre-first-byte and mid-stream timeout, and stream error event denial.
5. Request denial before claim for wrong route/method/model/hash, a
   non-streaming body, duplicate keys, cancellation, revocation, expiry,
   and a second run ID or task identity.
6. Claim/store failure before callback: zero forwarding. Callback failure,
   parser failure, response-evidence write failure, and crash after claim:
   no refund and replay/second-attempt denial after reopening the store.
7. Retry, redirect, fallback, and auxiliary-call attempts: each must be
   visible as an attempted second call and denied even when the first stream
   fails; zero hidden success. A one-start limit alone cannot pass this.
8. Source/package SDK tests, separately, show the exact emitted body and
   verify `maxRetries: 0` for the selected task path. Title generation or
   other internal calls must be disabled, isolated, or explicitly denied.
9. v1 regression: unchanged golden binding ID and EA92F `stream: true`
   denial. No v2 fixture may replace a historical v1 fixture.

Fake tests prove parser and accounting behavior only. They do not prove
receiver egress containment, installed-binary provenance, CPU-only model
policy, trusted capture issuance, or EA92S exact mapped-byte identity.

The unchanged v1 binding and offline-handler tests passed 140/140 with
`py -3.14 -m pytest -q -p no:cacheprovider` against the two dedicated test
files. The bundled Codex Python has no pytest, so it was not used for this
gate. No new v2 parser test exists yet; this is a design checkpoint.

## Decisions required before implementation or freeze

- Bind an exact source/package/receiver target or explicitly keep v2
  implementation as an inert parser only. The EA92BS SDK test is not an
  installed-binary attestation.
- Decide whether the candidate SSE framing and bounds match the pinned SDK's
  accepted response. Capture a networkless successful SDK stream fixture
  and a synthetic failure fixture, including any usage or error event shape.
- Specify the v2 schema, transport-contract ID, response evidence record,
  and durable reservation/result transition. Existing EA92C/F are
  acceptance-owned and do not create a production listener.
- Prove receiver-to-gate-only and gate-to-approved-upstream-only egress in
  the target deployment; loopback URL configuration alone is insufficient.
- Review the EA92K 13-derivation downstream roll using exact new target
  bytes. Do not alter the Kilo pin, existing durable records, or historical
  authority to force an ID match.

`V1=FROZEN_UNCHANGED`, `V2_TEST_SURFACE=DESIGN_CANDIDATE`,
`V2_SCHEMA=NOT_FROZEN`, `V2_IMPLEMENTATION=NOT_STARTED`,
`INSTALLED_RECEIVER_PROOF=HOLD`, `TRUSTED_CAPTURE_ISSUER=HOLD`,
`EA92S_EXACT_MAPPED_BYTE=REJECT`, `PRODUCTION_READINESS=HOLD`.
