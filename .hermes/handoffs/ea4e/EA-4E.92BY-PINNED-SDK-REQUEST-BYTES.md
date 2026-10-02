# EA-4E.92BY Pinned SDK Request Bytes

Non-live continuation from EA92BX at
`6373bf3ad5605416682c59690118c6b4c5b7a697`. The pinned SDK harness
now retains its injected transport's raw request string before JSON parsing
and asserts byte-for-byte equality with a shared synthetic request fixture.
The fake one-call gate consumes that same fixture under a request-hash-bound
durable claim. No installed OpenCode receiver or real provider was used.

## Exact scoped finding

For the existing simple `streamText()` prompt, pinned
`@ai-sdk/openai-compatible` 2.0.41 and `ai` 6.0.168 emit the fixture in
`tests/hermes_core/fixtures/ea4e92by_sdk_request.json` as one POST body.
The raw UTF-8 body has SHA-256
`ebfb27264f02c96ab3f6655a32ad85e4c7d4c29bf3901ca583557e877a51ed9a`.
Two inert observations matched, and the SDK test now fails if its emitted
body differs. The Python test binds that hash to an EA92C qualification
scope, passes the exact fixture to EA92BW, verifies the raw SSE capture,
and denies replay. The request fixture's terminal file newline is removed
by both readers before comparing or sending; it is not part of the body.

This closes the prior **SDK fixture versus fake gate** byte mismatch for
this simple synthetic prompt. It does not establish what an installed
OpenCode process emits for a delegated task. The source's title-generation
path can request retries, and a whole session may create auxiliary calls;
none are qualified by a single SDK fixture.

## Verification

The pinned SDK harness passed using its injected, networkless fetch and
process/network tripwires. It reported one successful streaming request,
one attempt on synthetic 503 with `maxRetries: 0`, three attempts with
`maxRetries: 2`, and one non-streaming `generateText()` request. Real
receiver starts and network calls: 0.

The focused EA92C/D/F/J/BV/BW Python ladder passed 227/227 on installed
Python 3.14. The new case verifies exact fixture hash, accepted fake
one-call capture and replay denial. It does not run a production listener,
real provider, GPU or ComfyUI.

## Remaining boundary

Installed-binary source/SDK provenance, receiver-generated request bytes,
auxiliary-call behavior, enforced egress, v2 schema and target IDs,
trusted capture issuer, EA92S exact mapped-byte proof and the EA92K
downstream roll remain unclosed. A real one-start receiver probe requires
a separate exact bounded authorization; this checkpoint grants none.

`PINNED_SDK_REQUEST_BYTES=QUALIFIED_INERT`,
`FAKE_GATE_EXACT_FIXTURE=PASS`, `INSTALLED_RECEIVER_PROOF=HOLD`,
`V2_SCHEMA=NOT_FROZEN`, `TRUSTED_CAPTURE_ISSUER=HOLD`,
`EA92S_EXACT_MAPPED_BYTE=REJECT`, `PRODUCTION_READINESS=HOLD`.
