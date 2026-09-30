# EA-4E.92BM Capture-Only Authority Boundary

Non-live design checkpoint at `8ec1362fc806ca32c038f7a8c8fdf3df2b74740d`.
This document grants no invocation, process, provider, production activation,
GPU, or ComfyUI authority. EA92S exact mapped-byte proof remains REJECT/HOLD.

## Source finding

`production_invocation_authorization_issuer.py` rejects every issue request
whose `runtime_scope` is not `production` or whose `delegation_class` is not
`governed`. `production_invocation_authorization.py` applies the same two
restrictions when evaluating an issued artifact. The `capture-qualification-only`
record in `ea4e92bh_fake_capture_admission.py` is acceptance-only, created by
fixture code, and cannot pass that production policy. Re-labeling it as
`production` would grant the wrong authority. The production issuer and
policy must not be relaxed to admit capture-only values.

`OpenCodeReceiverAdapter.execute()` can call its process implementation
directly; it does not itself validate capture or production authority.
`OpenCodeLiveBindingHarness` validates full production activation and is
explicitly forbidden for the prospective EA92A capture. The spool claim in
`OpenCodeLiveProcess.start()` prevents reuse of one run ID but neither issues
authority nor accounts for internal provider calls. These are three distinct
boundaries, not substitutes for one another.

## Proposed ownership for a later implementation

1. An external, explicitly requested capture-qualification issuer owns a
   *separate* versioned artifact and policy. It is not the production issuer,
   `ProductionInvocationAuthorization`, or the acceptance fixture. The artifact
   binds a fresh authorization ID, one run ID, exact receiver, task-byte hash,
   source commit, executable/config/transport/model identities, expiry,
   cancellation/revocation state, and one process-start budget. Its issuance
   and consumption must be restart-durable and collision/replay-denying. A
   capture artifact must be rejected by every production activation path.
2. A capture-only coordinator owns admission and ordering. Before any start it
   verifies the artifact, current identities, task bytes, containment policy,
   and independently enforceable or observable one-model-call budget; it then
   durably consumes the one-start authority. A failed or uncertain start does
   not refund it. It never constructs a `ProductionActivation` or invokes the
   production live-binding harness. Cancellation and revocation deny before
   start; after start they trigger bounded termination and a consumed/HOLD
   outcome, not retry.
3. The coordinator may use the existing OpenCode adapter/process transport
   only behind that admission boundary, with a fresh run namespace. The
   process controller owns raw stdout/stderr capture and cleanup; an
   independent acceptance verifier owns hash/lineage checks and offline
   replay. A parsed success string is not proof of provider count, complete
   streams, or cleanup.
4. The external issuer, coordinator, provider-control owner, and acceptance
   verifier must have separate canonical IDs and evidence. Neither the
   production durable store's generic `persist_issued`/`claim` methods nor
   an injected fake callback make a record live authority by themselves.

## Gate before implementation or any live packet

Freeze the capture artifact schema, issuer identity, trusted persistence
namespace, consumption ordering, crash recovery, cancellation/revocation,
and exact dependency closure. Freeze a provider/model containment mechanism
that proves one internal model call and the authorized CPU/network policy;
the current OpenCode configuration and CLI adapter do not prove this. Freeze
current executable/source/config identities and a secret-safe capture
destination. Test missing/wrong authority, cross-scope use in both directions,
identity drift, duplicate starts, concurrent claims, failed/uncertain spawn,
retry/fallback, over-budget calls, truncated/invalid streams, and uncertain
cleanup with process-free fakes. Re-run the affected authority, adapter,
offline-replay, sealed-aligned, and broad guarded gates against staged and
committed source. Only then request a *separate, exact, one-shot live*
authorization; this design is not one.

Historical EA4 capture remains `FAIL_MISSING_CAPTURE`. A prospective fresh
EA92 capture can close only its own current qualification obligation under
EA92A. Production readiness, trusted native creation, and real Kilo/OpenCode
execution remain HOLD.
