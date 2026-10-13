# EA-4E.92IL Fake Gateway / Delegated Ping Body Mismatch

Status: SOURCE REVIEW / NON-LIVE / WORKING PING BLOCKED.
Baseline: `c68d66f3ae95f618eda45171c3db35a48d5bd8b5`.

The pinned fake gateway in
`tools/hermes_core/container_images/ea4e92ew_kilo_fake_gateway/gateway.js`
responds with SSE content `EA4E_INERT_OK`. Its associated probe plan and
client assert that exact fixed response. That probe qualified the inert
HTTP exchange, not the delegated Kilo ping result.

`build_agent_text_ping_message()` instead requires one JSON object whose
task input hash and receipt hash match the current delegated attempt.
`validate_agent_ping_candidate()` rejects a literal `EA4E_INERT_OK` body.
The new 92IK preview correctly validates a synthetic JSONL text event, but
that event is not what the frozen gateway emits. Therefore current source
cannot prove a complete Kilo-to-gateway-to-Hermes ping, even if container
start and output retention were later qualified.

Narrow next non-live work:

1. Define an attempt-bound, deterministic fake response body from the
   already accepted task, lease and receipt; validate it with the existing
   ping schema before encoding a bounded OpenAI-compatible response.
2. Define exact one-request gateway admission and request/response hashes,
   retaining the old `EA4E_INERT_OK` probe as historical evidence only.
3. Requalify the revised gateway source, image and response transport under
   a new version/digest. Do not silently reuse the old pinned image.
4. Only then design a separately authorized, one-shot Kilo receiver probe
   with trusted daemon binding, containment, terminal capture and no real
   provider/model credential. OpenCode needs independent qualification.

This review changed no gateway, image, test, Docker object or runtime state.
Production activation and real receiver/model execution remain unauthorized.
The accepted local-container profile does not satisfy strict 92AT mapped-byte
proof, which remains HOLD.
