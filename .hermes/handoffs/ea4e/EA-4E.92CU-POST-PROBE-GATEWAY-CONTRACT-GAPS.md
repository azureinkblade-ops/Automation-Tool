# EA-4E.92CU post-probe Kilo gateway contract gaps

Status: NON-LIVE REVIEW / PRODUCTION GATEWAY HOLD
Baseline: `34f565bf6e0d4ca2a536fefff8d32d3fdaad52ca`

## What 92CR established

One pinned Kilo 7.8.3 inert run sent one streaming
`POST /v1/chat/completions` to the dummy loopback provider. The sanitized
request was 64,878 bytes with two messages. It included `stream_options`,
`tools`, `tool_choice`, and `max_tokens` alongside model, messages, and stream.
The request-body SHA-256 is evidence for that one prompt and process only.
No raw body, prompt, or authorization header was retained. Kilo also rewrote
its isolated dummy config after launch. See `EA-4E.92CR-KILO-SHAPE-PROBE-RESULT.md`.

## Gaps before a production gateway

1. **Request identity.** `KiloFakeScope.request_hash` is fixed before the
   injected request. That is appropriate for its acceptance fixture, but the
   92CR body hash cannot authorize a different delegated task. The actual
   Kilo-generated body for a future task has not been shown to be predictable
   before launch. Removing the hash check or accepting the first body from a
   bearer-token holder would loosen the authority boundary, especially while
   same-user peer identity remains unproved. A new, reviewed contract must
   bind the delegated task and one observed request body without letting an
   unrelated process consume the one-send budget first.
2. **Size bound.** The observed body was only 658 bytes below the current
   65,536-byte fake-provider and sanitizer cap. This is not evidence that
   longer prompts or different tasks fit. Do not freeze 65,536 bytes as the
   production maximum or silently truncate. A production bound must be
   selected with measured headroom, explicit denial/accounting, and fake
   tests at and above the limit. The durable upstream-send budget must never
   be refunded after a send claim.
3. **Schema and forwarding.** The current fake gateway checks model, message
   array, and streaming flag after matching its exact fixture hash. A future
   dynamic-body contract needs explicit allowed fields, nested limits,
   duplicate-key rejection, model/route binding, and streaming-response
   bounds before any upstream forwarding. The 92CR field-type summary is a
   single observation, not a general production schema.
4. **Config and credentials.** The prelaunch config bytes were verified, but
   Kilo reformatted that dummy config and added `$schema` during the run.
   Separate the immutable authorized config input from mutable runtime output
   in any future binding. The upstream credential must stay gateway-only;
   a child local token is not process identity. No production token handoff
   is qualified by this probe.

## Next qualified work

Design and fake-test the new request-identity and size contract against
synthetic bodies only, after the local adversary/peer-isolation model is
settled. Roll separate custom-provider transport and model IDs; do not reuse
the existing sealed free-model route. The independent 92S exact mapped-byte
proof remains HOLD. No new receiver, provider, model, GPU, or ComfyUI
operation is authorized by this review.
