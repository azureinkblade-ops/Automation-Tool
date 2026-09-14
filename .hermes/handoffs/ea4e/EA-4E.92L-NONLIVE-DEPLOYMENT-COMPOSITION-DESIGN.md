# EA-4E.92L Non-Live Deployment Composition Design

Baseline: af0057eea84b8fd9dad2c208a8cdfbfd927576ac.
Status: DESIGN RECORDED / TARGET ARTIFACT FREEZE HOLD.
Scope: OpenCode governed delegation composition requirements only.
No implementation, deployment, registration, authority issuance or live use.

## Existing Surface and Limits

EA92I freezes hermes.opencode-provider-binding/v1. EA92J implements strict
build/parse and verification of supplied runtime/config/four policy byte sets.
Those checks establish identity agreement, not trusted acquisition or enforcement.
EA92K identifies 13 shared core derivations and ten additional reviewed sources;
it does not establish a complete deployment/import/fixture closure.
production_deployment_composition.py composes Kilo and must not be repurposed
or treated as an already-qualified OpenCode deployment owner.

This document specifies required roles, not installed components or approved
operator identities. Actual owners, policy bytes and target paths remain unbound.
Do not replace a missing artifact with this requirements document's digest.

## Ownership and Acquisition

| Artifact | Required trusted owner | Acquisition and acceptance | Current state |
| --- | --- | --- | --- |
| Binding manifest | Hermes reviewed composition owner | Strict EA92J parse, expected registered ID, independently reviewed references | No real target frozen |
| Executable | Operator-approved deployment owner | Read exact file bytes without execution; verify qualified version provenance and hash; record file identity | Historical pin is not fresh admission proof |
| Isolated config | Deployment owner, never receiver/task | Read exact raw bytes; inspect effective model, package and endpoint selection with secrets omitted from public evidence | Existing direct-provider config is not gate-qualified |
| Gate contract | Hermes authority/gate owner | Reviewed source/contract bytes, durable ledger identity and fake qualification evidence | No production artifact frozen |
| Egress policy | Host containment owner | Reviewed policy bytes plus fake validation and separately authorized applied-policy evidence | Enforcement unproven |
| CPU policy | Local model deployment owner | Explicit backend/model/device policy bytes plus separately authorized effective-runtime proof | CPU-only execution unproven |
| Cleanup contract | Request lifecycle owner | Exact resource ownership, idempotent teardown and recovery evidence | OpenCode-specific artifact absent |

Runtime package provenance and effective SDK behavior belong to an external
qualification envelope bound to the manifest ID and exact source bytes. Do not
add fields to frozen v1 or silently change constants. If that envelope cannot
prevent package drift, HOLD and request a reviewed contract revision.

No filesystem scan here asserts global absence. The reviewed source surface
does not supply the required real policy composition.

## Required Admission Sequence

1. Validate independent governing commit, operator and request authority;
   resolve trusted deployment artifacts, not receiver-provided references.
2. Verify expected binding ID with exact runtime/config/policy bytes using EA92J.
   Verify qualified package provenance, effective config and store ID/epoch.
3. Establish enforceable artifact immutability and restricted receiver access.
   Record trusted file/resource identity and recheck immediately before admission.
   Hash-before/hash-after alone is not adequate TOCTOU containment.
4. Check durable cancellation/revocation and expiry at the atomic gate reservation
   decision. Record authorization, delegation, execution/launch attempts, binding,
   request body hash and reservation lineage without conflating their identities.
5. Durably consume at most one upstream-call slot before sending upstream bytes.
   Ledger or anchor ambiguity denies forwarding; crash/timeout never refunds.
6. Record entered/terminal outcome and bounded response evidence. Return result
   through Hermes lineage validation; the receiver cannot fabricate completion.
7. Request-owned teardown runs on success, denial after resource acquisition,
   exception and recovery. Persist cleanup failure; do not report clean completion
   while owned resources remain unresolved.

Activation authorization consumption and provider-call slot consumption are
different durable transitions. One must not imply or reset the other. Cancellation
before atomic reservation denies a call; cancellation after admission prevents
subsequent work but cannot promise to retract already-sent upstream bytes. Any
such in-flight activity must remain accounted and evidence-preserved.

## Policy Artifact Requirements

Gate: exact route/body bounds, non-streaming only, no redirect/retry, maximum one
call; trusted durable reservation owner, cancellation serialization, anchor/store
rollback handling and audit-write failure semantics. Fixture request booleans
are not durable authority. Actual SDK body must be captured in fake qualification.

Egress: receiver may reach only its owned gate; gate may reach only the approved
upstream. Deny direct model endpoint, alternate loopback, DNS, proxy/environment
overrides and child-process bypass. Loopback URL restrictions alone do not enforce
this. If the receiver cannot be contained, composition remains HOLD.

CPU: qualify exact local backend/model configuration and effective device policy.
Do not infer CPU use from model name, absence of CUDA toolkit or request text.
No GPU generation or ComfyUI interaction is part of this integration design.

Cleanup: identify only resources created/claimed by this request, with ownership
tokens and durable recovery records. Never kill unrelated processes, delete user
files, free unrelated GPU work or modify Studio Bible/image-pipeline resources.
Owned listeners/connections close; ambiguous process identity fails closed to
operator recovery, not broad process termination.

## Non-Live Qualification Before Freeze

- Fake byte acquisition: missing, mismatched, replaced, untrusted or writable
  artifact; effective config override and package drift all deny admission.
- Pure verifier agreement with real reviewed supplied bytes, never fixture IDs.
- Fake SDK adapter proves exact effective body/model and one non-streaming route.
  Streaming, extra calls, redirects, retry or unsupported SDK behavior deny.
- Concurrent/restarted reservation, expiry, cancellation/revocation race,
  ledger/anchor corruption and pre/post-send crash preserve at-most-once accounting.
- Fake teardown proves owned-only cleanup, repeated recovery and durable failure.
- Negative tests reject stale shared authority IDs for both OpenCode and Kilo.
- Process/network/model/GPU tripwires remain active; no actual receiver or model
  process is needed for this qualification.

These are acceptance requirements, not test results. No new tests were run or
implemented by this evidence-only design step. EA92K's six passing current-ID
tests remain historical evidence for its exact baseline, not deployment proof.

## Next Boundary and Checkpoint

Design evidence may be checkpointed independently. Real target freeze requires
reviewed policy artifacts, named trusted owners, exact supplied runtime/config
bytes and a qualified fake SDK/composition path. Until then proposed binding and
downstream IDs remain UNRESOLVED_TARGET_BINDING_NOT_FROZEN.

Next safe implementation slice: isolated fake-only composition/acquisition
qualification with supplied immutable evidence and no production owner wiring.
Inspect existing fixture interfaces before authorizing its minimal file surface.
Applied containment, config changes, listeners, backend/device checks requiring
execution and any receiver/provider/model invocation need a separately bounded
deployment/live authorization; general continuation is not a one-shot envelope.

No current registry/sealed ID, Kilo runtime pin or durable history is modified.
No source-closure PASS or production-readiness claim. No deletion. No live activity.
