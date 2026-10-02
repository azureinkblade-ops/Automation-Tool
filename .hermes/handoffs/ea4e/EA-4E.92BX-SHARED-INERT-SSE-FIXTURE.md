# EA-4E.92BX Shared Inert SSE Fixture

Non-live continuation from EA92BW at
`64618a002801a4a7cf00b4aa57ea2cffb2e2ad7b`. This checkpoint makes the
existing successful synthetic SSE response a shared fixture. The pinned SDK
test, pure Python inspector, and fake one-call gate now consume the same
fixture bytes. No OpenCode receiver, model, provider endpoint or listener
was started.

## Scope

`tests/hermes_core/fixtures/ea4e92bx_success.sse` contains two synthetic
OpenAI-compatible chat-completion chunks and a terminal `[DONE]` line. Both
test readers append one LF to complete the final blank-line delimiter;
their injected response bytes are therefore identical.
The previously qualified Node SDK test reads it through its injected fetch
response and still requires `streamText()` to return `ok` in one request
with `stream: true`. It still checks the pinned package versions and lockfile
integrities, zero-retry and two-retry synthetic 503 behavior, and one
non-streaming `generateText()` request. The Python tests read the same file:
EA92BV validates its framing and EA92BW validates one durable fake claim,
raw capture, and replay denial.

This is a shared *synthetic response*, not a capture from the installed
OpenCode binary. The request body in the Python gate remains a synthetic
fixture with its own SHA-256; this checkpoint does not claim it equals the
SDK's emitted body or an installed receiver's effective request.

## Verification

The pinned `@ai-sdk/openai-compatible` 2.0.41 / `ai` 6.0.168 SDK harness
passed with its existing process/network tripwires and injected transport:
one successful `streamText` request, one synthetic 503 attempt with
`maxRetries: 0`, three with `maxRetries: 2`, and one non-streaming
`generateText` request. Reported real network calls and receiver starts: 0.

`py -3.14 -m pytest -q -p no:cacheprovider` across EA92C/D/F/J/BV/BW:
226 passed, zero failed. The shared fixture is checked in both the pure
inspector and fake one-call composition. The Python tests use temporary
fixture stores; no live authority or production state is touched.

## Remaining boundary

The next target proof must bind the selected SDK request body, retry and
auxiliary-call behavior to an exact installed receiver build, or use a
reviewed trusted build-provenance chain. A one-start inert receiver probe
requires separate bounded authorization. V2 schema, enforced egress,
trusted capture issuer, EA92S exact mapped-byte identity, downstream ID
roll and production readiness remain unclosed. The synthetic success
fixture cannot close any of those by itself.

`SDK_SYNTHETIC_SSE_COMPATIBILITY=PASS`,
`FAKE_ONE_CALL_SHARED_FIXTURE=PASS`,
`INSTALLED_RECEIVER_PROOF=HOLD`, `V2_SCHEMA=NOT_FROZEN`,
`TRUSTED_CAPTURE_ISSUER=HOLD`, `EA92S_EXACT_MAPPED_BYTE=REJECT`,
`PRODUCTION_READINESS=HOLD`.
