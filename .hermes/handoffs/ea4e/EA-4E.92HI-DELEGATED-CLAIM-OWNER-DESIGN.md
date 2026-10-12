# EA-4E.92HI Delegated Claim Owner Design

Status: SOURCE DESIGN / NON-LIVE. Parents: EA-4E.92HF-HH.

## Source boundary

The general `ProductionInvocationAuthorizationIssuer` does not consult the
delegation authority database. `ProductionInvocationAuthorizationPolicy` can
claim a durable authorization with an expected execution request ID, but
that argument is optional for general callers. The delegated receiver-start
fence is a separate one-shot transaction in the delegation database. No
current caller owns all three operations for a real Kilo/OpenCode accepted
attempt. The existing real executors generate fresh IDs and are not such an
owner.

## Required owner sequence

1. Load the exact durable accepted STARTED witness and the existing 92HF
   bridge. Resolve the same executor binding. Build the 92HH issue request
   and run 92HG preflight. Pin one durable invocation-authorization store and
   its anchor; do not use an in-memory or alternate store on restart.
2. The external issuer may persist the exact request. Exact replay may return
   its existing authorization, but no different issue request, nonce, TTL,
   receiver, binding, or execution request may replace it. An issued but
   unconsumed authorization is not a process-start permit.
3. Immediately before irreversible consumption, revalidate active delegated
   authority, exact bridge/binding, authorization payload, and expiry. Call
   `claim_for_execution` with `expected_execution_request_id` explicitly set
   to the reserved bridge ID. A failed/ambiguous claim must not launch.
4. After a successful durable authorization claim, claim the receiver-start
   fence for the same accepted attempt. The fence transaction orders a
   cancellation/revocation committed in the delegation database before the
   fence; such a prior cancellation must deny. A cancellation committed
   after the fence is an in-flight cancellation, not proof that no process
   started. Its handling must be explicit in the later process owner.
5. Only a separate trusted process owner may start the actual receiver once,
   using the accepted lineage and exact binding. It must record observable
   process identity and terminal bytes and commit terminal capture before
   publishing a result. The existing UUID-generating real executors cannot
   be substituted for this owner.

## Crash and retry contract

| Last durable point | Restart behavior |
| --- | --- |
| Bridge reserved, no issued authorization | Revalidate; exact issue request may proceed. |
| Authorization issued, not consumed | Inspect exact pinned store; revalidate current authority before claim. |
| Authorization consumed, fence absent | UNKNOWN; no automatic reissue or second claim/start. |
| Fence claimed, no terminal capture | RECEIVER_START_UNKNOWN; reconcile only, no second start. |
| Terminal capture committed | Verify lineage and return the captured result; do not rerun. |

The two SQLite stores do not share an atomic transaction. A preflight or
read-time check is never sufficient to overcome a later cancellation. If
the authorization store's identity, anchor, consumed state, or claim outcome
cannot be proven after a crash, deny or retain UNKNOWN. Do not infer success
from a caller-provided `ExecutionOutcome`.

## Non-live acceptance for implementation

- Fake Kilo and OpenCode accepted attempts; exact one-claim/one-fence path.
- Changed request, nonce, TTL, receiver, binding, enablement, executor, or
  store identity denied; unrelated/general issuer behavior unchanged.
- Cancel/revoke before issue, before claim, and before fence; expiry at every
  boundary; concurrent callers; restart after every durable point.
- Inject faults before/after authorization commit and before/after fence
  commit; ambiguous state remains UNKNOWN and never launches twice.
- No app startup/route/scheduler hook, receiver process, model, network,
  Docker, GPU, ComfyUI, or production activation in this qualification.

This design does not authorize live execution. `PRODUCTION_READY=NO`.
