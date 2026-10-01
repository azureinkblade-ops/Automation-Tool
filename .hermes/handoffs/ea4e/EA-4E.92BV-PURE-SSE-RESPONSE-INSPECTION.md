# EA-4E.92BV Pure SSE Response Inspection

Non-live implementation continuation from EA92BU. This checkpoint adds only
a pure response inspector and its dedicated fake-only tests. It does not
modify the frozen v1 binding or EA92C/F admission, create a v2 binding,
start OpenCode, listen on a socket, or call a provider/model.

## Scope and result

`tools/hermes_core/opencode_sse_response.py` accepts injected `(bytes,
elapsed_ms)` chunks, status and response headers. It requires an exact 200
`text/event-stream` uncompressed response, 65,536 raw bytes or fewer, 128
events or fewer, 4,096 bytes or fewer per line, 1,024 chunks or fewer, and a
30,000 ms fake-clock deadline. It accepts LF/CRLF framing, one JSON object
per nonterminal `data:` event, and a single final `[DONE]` event. It denies
malformed UTF-8, duplicate JSON keys, nonfinite constants, unsupported SSE
fields, error payloads, truncation, duplicate terminal, trailing content,
metadata mismatch and limit overruns. The returned immutable evidence keeps
the exact raw response bytes, SHA-256, event count and chunk count.

The chunk limit is a necessary refinement of EA92BU's candidate bounds:
empty chunks otherwise evade byte and event counters. This is still an
acceptance-only parser and candidate policy, not a deployed timing or
egress boundary. Its fake elapsed time cannot prevent a real upstream
iterator from blocking before the next chunk.

The existing EA92BS inert SDK harness already contains a successful
synthetic SSE fixture. EA92BU's call to capture one should therefore be
read as requiring exact fixture retention/compatibility against a future
v2 target, not as evidence that the successful SDK shape was absent.

## Verification

`py -3.14 -m pytest -q -p no:cacheprovider` across the new dedicated test,
frozen v1 binding test, and EA92F offline handler test: 167 passed, zero
failures. The new test covers chunk/UTF-8/CRLF splits, metadata, malformed
framing and JSON, exact and exceeded bounds, fake-clock deadline, empty
chunk flood and trailing content. The Codex-bundled Python does not have
pytest, so the installed Python 3.14 runtime was used. No broad-suite or
installed-receiver qualification is claimed.

## Unclosed gates

The pure inspector is not connected to a durable call reservation or raw
evidence store. It cannot attest receiver-to-gate or gate-to-upstream
egress, internal retries, title generation, installed-binary provenance,
CPU-only policy, trusted capture issuance, or EA92S exact mapped-byte
identity. A subsequent fake-only v2 gate must integrate no-refund durable
claim and failure/replay accounting before any bounded receiver probe is
considered. V2 schema/IDs and the 13 downstream EA92K derivations remain
unfrozen. No production or live authority follows from these tests.

`V1=FROZEN_UNCHANGED`, `V2_PURE_PARSER=FAKE_ONLY_VERIFIED`,
`V2_GATE=NOT_IMPLEMENTED`, `V2_SCHEMA=NOT_FROZEN`,
`INSTALLED_RECEIVER_PROOF=HOLD`, `TRUSTED_CAPTURE_ISSUER=HOLD`,
`EA92S_EXACT_MAPPED_BYTE=REJECT`, `PRODUCTION_READINESS=HOLD`.
