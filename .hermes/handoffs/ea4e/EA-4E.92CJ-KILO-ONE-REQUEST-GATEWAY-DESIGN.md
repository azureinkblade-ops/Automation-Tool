# EA-4E.92CJ Kilo one-request gateway design

Status: NON-LIVE DESIGN ONLY / IMPLEMENTATION AND LIVE USE NOT AUTHORIZED BY THIS FILE
Baseline: `132fbbabc729e1e2ebdfc555a49f867ff1a6967c`

## Decision

Keep the exact one-provider-request ceiling for the next Kilo pilot. A
one-process or one-adapter-call limit is insufficient: the historical live
runner derives its `model_invocation_count` from Hermes-side call counts,
not independently counted upstream requests (92CI).

Kilo's documented `steps` setting limits agentic iterations, not provider
requests or provider retries. Do not use it as the request ceiling. Kilo
documents a custom OpenAI-compatible provider with a configurable `baseURL`,
so a local gateway is a candidate route, not yet a qualified route:

- https://kilo.ai/docs/customize/custom-modes
- https://kilo.ai/docs/code-with-ai/agents/custom-models
- https://kilo.ai/docs/gateway

## Proposed boundary

Kilo would be configured for one attempt-scoped loopback endpoint, with a
single pinned model mapping. The endpoint would accept only the authorized
completion path and one attempt-bound credential. Before opening any upstream
connection, it would atomically claim a durable request budget keyed by the
governed execution attempt. Request #2, a duplicate after restart, an
unrecognized path, or an expired/revoked attempt would be denied locally.
The gateway would make at most one upstream HTTP request with redirects,
automatic retries, and fallback disabled. It would stream the sole response
without buffering it unboundedly and record request/response metadata without
prompt text, tokens, or secrets. Timeout or upstream failure still consumes
the budget; no automatic reissue.

The exact upstream API path and response/streaming protocol must be discovered
with a fake endpoint before implementing forwarding. Do not assume the
currently pinned Kilo provider uses OpenAI Chat Completions or that switching
to a custom provider preserves the current model identity or free-tier access.
Do not change the existing fixed argv, profile, credential reference, or
sealed IDs merely to make a fake test pass.

## Required non-live qualification

1. Under a separate exact authorization for an inert receiver-process probe,
   observe the pinned Kilo 7.8.3 CLI against a local fake provider with no
   real model credentials. Record all attempted paths, method, request count,
   response format, streaming behavior, and any retry. The fake must never
   forward traffic. Do not launch Kilo as part of this design checkpoint.
2. Freeze the exact custom-provider config, model mapping, executable hash,
   loopback address, credential source, request schema, and gateway source
   identity. Review how Kilo obtains a local token without exposing the
   upstream credential to the child or repository.
3. Test the gateway with fake transport: concurrent first/second requests,
   duplicate/replay after restart, crash between durable claim and send,
   cancellation/revocation, timeout, redirect, upstream error, malformed
   response, streaming truncation, and unauthorized local callers. For all
   cases, prove upstream send count is never greater than one per attempt.
4. Roll every affected transport, model, credential, authorization, and
   dependency-closure contract. Re-run focused and committed-tree fake-only
   acceptance suites. Preserve raw inherited failures in the report.
5. Only after a synchronized reviewed commit, issue a separate exact live
   authorization for one attempt, one receiver process, one gateway budget,
   one upstream request, fixed prompt/model, timeout, output caps, audit,
   and teardown. A fake pass alone is not live readiness.

## Stop conditions

Any uncertain path/protocol, unsupported model mapping, unbound credential,
uncontrolled network egress, gateway retry, or missing durable budget is a
HOLD. No real Kilo receiver, provider, model, production activation, GPU,
or ComfyUI call is authorized here. The EA-4E.92S mapped-byte proof remains
REJECT/HOLD independently of this Kilo route.
