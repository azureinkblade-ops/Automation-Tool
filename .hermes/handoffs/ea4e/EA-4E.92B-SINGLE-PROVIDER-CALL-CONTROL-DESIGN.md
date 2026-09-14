# EA-4E.92B Single Provider Call Control Design

Status: NON-LIVE DESIGN COMPLETE; IMPLEMENTATION NOT QUALIFIED.
Baseline: ed951c0cd1117582cc44f48a0ff7fd8ea3f9ca16.
EA92 live task/process/model budget remains unused.

## Findings and limits

The reviewed committed interfaces limit executor/adapter tasks, not individual
provider requests. opencode_invocation_authorized_live.py derives model counts
from adapter or executor calls. live_opencode_dispatch.py limits invocations.
The installed opencode-ai package inventory contains binary payloads and wrapper
metadata, not provider-loop source. The pinned source inspection report does
not establish an enforceable single-provider-request limit. This is bounded
negative evidence, not proof that no upstream feature exists.

Do not execute the runtime for discovery under this design authorization.
Do not infer max steps, retry settings or task wording enforce the live budget.
The configured backend is ollama/qwen3:14b; its actual current model-binding
identity, provider readiness and CPU-only capability still need verification.

## Selected minimal architecture

EA92 capture harness -> pinned OpenCode -> qualification-only loopback provider
gate -> exact qualified provider endpoint/model.

The gate owns the only upstream forwarding capability. It accepts only the
frozen inference route/method/model and bounded request body for one run.
All other routes, models, redirects, discovery calls, retries and fallbacks
are denied before forwarding. No general-purpose proxy or URL supplied by the
receiving agent. Only an injected transport in fake qualification; no default
network transport until separately authorized implementation review.

Bind the run to exact source SHA, authorization/task IDs and hashes, receiver,
executable, transport, model and deployment identities. Do not claim that the
provider request body equals the original task bytes: OpenCode may construct
messages. Capture and correlate both task input and effective provider input.
Record any mismatch against a frozen effective-request policy as a denial.

## Durable consume-before-forward sequence

1. Validate request and immutable run binding, scope, cancellation and expiry.
2. In one SQLite transaction, conditionally reserve an UNUSED run as CONSUMED
   and append a request-digest/sequence record. Exactly one claimant can win.
3. Commit and durably confirm reservation before obtaining forwarding authority.
4. Forward once with redirects and all transport retries disabled.
5. Persist provider-call start, terminal outcome, bounded response digest/bytes
   and exit/cleanup correlation. Do not store secrets or unrestricted headers.

After reservation, timeout, disconnect, restart or uncertain forwarding never
refunds the slot. A crash between commit and request forwarding wastes the
single slot; it does not permit another attempt. Provider acceptance cannot
be made transactional with SQLite. Do not claim exactly-once successful model
execution; the enforceable property is at-most-one outbound inference request.
Report actual accepted/completed model execution only when provider evidence
establishes it; otherwise report unknown and HOLD, not fabricated zero or one.

Duplicates and concurrent requests receive a terminal budget denial without
upstream activity. Gate restart reopens the same bound database, not a newly
initialized budget. Missing, corrupt, replaced or unverifiable store identity
fails closed. Reuse the established durable store/identity pattern where its
contract actually applies; do not weaken it or invent an unrelated reset API.

## Critical deployment qualification

Merely pointing a provider config at the gate does not prove no bypass.
Qualify the isolated configuration/provider resolver, deny alternate endpoints,
ambient/project config and direct upstream egress from the receiver. If the
existing runtime containment cannot enforce that, stop for a scoped deployment
control design instead of treating configuration as complete network isolation.

Changing provider baseURL to the gate changes effective deployment identity.
Review transport/model/deployment binding material and reseal every genuinely
affected contract before live admission. Preserve historical binding evidence;
never declare the old binding unchanged without proving its canonical material.
Do not use the production activation harness or issue production invocation
authorization merely to run this qualification.

GPU authority remains off. No live Ollama task is admitted until CPU-only
execution compatible with the qualified binding is demonstrated without model
generation, or a separately bounded GPU authorization is supplied. Altering
model settings silently to force CPU execution is not permitted.

## Required fake-only qualification

An injected fake upstream must count forwarding calls independently of gate
counters. No real socket, provider, process, receiver, model, GPU or ComfyUI.
Required tests (planned, not run in this design):
- First valid request forwards once; duplicate never forwards.
- Concurrent distinct requests reserve only one forwarding slot.
- Crash before reservation allows no forwarding; crash after reservation never
  permits a second forwarding attempt after reopen.
- Timeout, disconnect, uncertain response and terminal error never refund.
- Wrong run/task/binding/model/endpoint, expired/revoked/cancelled authority and
  malformed/oversized request deny before forwarding.
- Missing/corrupt/replaced durable state fails closed; no automatic reset.
- Redirect/retry/fallback paths denied; receiver bypass fails deployment review.
- Response streaming retains bounded authentic bytes with truncation and reader
  state explicitly reported; secret-bearing output holds the checkpoint.
- Terminal cleanup closes only owned resources; evidence is never deleted.

Require working, staged-only and committed-tree fake verification, zero real
runtime audit events, applicable predecessor/binding/cleanup regressions and
zero new broad failures. A pure fake gate proves admission logic only, not
runtime egress containment or a successful real provider call.

## Authorization boundary and next slice

EA92B changes documents only. No implementation, tests, provider configuration,
binding IDs or runtime state were changed. No model-call enforcement PASS.

Next implementation scope must explicitly authorize the testable reservation/
accounting component and injected transport, exact files, durable state identity
contract and fake-only gate. Live forwarding remains absent. Deployment/binding
impact must then be qualified separately before resuming the one-shot EA92.
If these controls cannot be realized without prohibited production changes,
EA92 remains HOLD. Do not silently reinterpret its one-model-call budget as
one CLI task. Any less strict task-only budget requires a new explicit packet.
