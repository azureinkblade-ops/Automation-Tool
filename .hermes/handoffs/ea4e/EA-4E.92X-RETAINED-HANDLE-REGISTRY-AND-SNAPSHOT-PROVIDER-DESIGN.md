# EA-4E.92X Retained-Handle Registry And Snapshot-Provider Design

## Disposition

DESIGN COMPLETE / implementation not started / native execution hold.

This checkpoint freezes the in-memory watcher ownership contract required
before a concrete NQ-12 snapshot provider can exist. It authorizes no native API
call, process launch, handle duplication, process/thread query, termination,
cleanup, receiver/model invocation, production activation, network, GPU or
ComfyUI activity.

## Governing state

- Branch: feature/ea4e67-kilo762-roll
- Synchronized parent: 95a01fc4c7f03c7461df6d8b7f12f054a23cf803
- Durable binding schema: hermes.ea4e92s-probe-evidence-store/v2
- Reconciliation boundary: exact binding enforced by EA-4E.92W

## Problem

The durable `ObserverResourceBinding` intentionally stores opaque token hashes,
PID/TID and creation identities, not raw native handles. A future provider must
therefore resolve the three tokens only inside the exact watcher instance that
retained the handles before broker launch. Reopening by bare PID/TID or treating
the broker's process-local job-handle integer as durable would permit reuse or
cross-process identity confusion.

There is also a lifecycle distinction that must remain explicit. Open retained
handles can be queried but are not closed. Closed handles cannot be queried.
Consequently, a snapshot provider cannot truthfully infer
`owned_handles_closed=True` by querying already-closed handles. Clean terminal
evidence must come from a watcher-owned cleanup transition that captures final
native evidence before closure and leaves an immutable tombstone afterward.

## Frozen ownership model

One watcher instance owns one in-memory registry. Its canonical UUID is fixed
at construction and must equal every accepted durable binding.

For one NQ-12 request, registration atomically retains:

- the exact `ObserverResourceBinding`;
- one job handle, one process handle and one primary-thread handle;
- the PID/TID and process/thread creation identities already present in the
  binding;
- a one-shot lifecycle state and no authority beyond those exact resources.

The three opaque SHA-256 token identities are distinct registry keys. Raw
handle values never enter SQLite, JSON, logs, evidence documents or provider
results. A registry restart or watcher-instance change loses resolution
authority and must fail closed; it never reconstructs ownership from PID/TID.

## State machine

`EMPTY -> RETAINED -> CLEANED`

- `EMPTY`: no token or handle is known.
- `RETAINED`: all three exact handles are owned and queryable. Exact replay of
  identical registration is idempotent; any drift conflicts.
- `CLEANED`: handles are no longer resolvable. The registry retains only the
  exact binding and immutable cleanup tombstone. Registration, handle lookup,
  replacement and a second cleanup transition are denied.

No delete, reset, token reuse, PID reopen, fallback lookup or transition back to
`RETAINED` exists.

## Resolution contract

Resolution requires the complete binding plus the expected watcher UUID and
durable PID/TID. The registry validates all three opaque tokens and every
binding field before returning a short-lived value object containing the exact
three retained handles. It performs no native operation itself.

Unknown token, partial match, wrong watcher, creation-time drift, PID/TID drift,
duplicate token, malformed handle, cleaned state or registry loss is an unknown
outcome and yields no handle.

## Native snapshot-provider contract

The future provider receives the validated durable binding from EA-4E.92W and
resolves it once through the registry. While state is `RETAINED`, injected
native query functions must independently verify:

- process and thread creation times still equal the binding;
- the exact process/thread handles correspond to the durable PID/TID;
- job active-process count is bounded and canonical;
- process/thread presence is reported without opening another handle.

The provider returns `owned_handles_closed=False` for every live query. It has
no cleanup, termination, close or retry authority.

When state is `CLEANED`, the provider may return only the immutable tombstone;
it performs no query against closed handles. A tombstone can confirm cleanup
only when it records the exact cleanup order, zero active owned processes,
process/thread absence, successful closure of all three exact retained handles,
and one positive monotonic observation time.

## Cleanup-owner contract

A separate watcher-owned cleanup operation is required. It alone may:

1. revalidate the exact binding and retained handles;
2. collect final native state;
3. execute the frozen order `TERMINATE_JOB`, `CLOSE_THREAD`, `CLOSE_PROCESS`,
   `CLOSE_JOB`;
4. verify every exact owned handle was closed;
5. atomically replace handle resolution with one immutable tombstone.

Partial cleanup, close ambiguity, unexpected survivor, identity drift,
query failure or tombstone-write failure remains unknown. No clean claim is
permitted and no later probe may start until separately reconciled.

## Concurrency and replay

- one registry owner thread at a time;
- one registered NQ-12 resource set per request;
- one cleanup transition;
- exact registration replay is idempotent only while retained;
- snapshot observation is read-only and may occur once per controller call;
- no automatic retries;
- no parallel cleanup and observation;
- no cross-request token sharing.

The implementation must serialize every transition and return immutable copies,
not mutable registry internals.

## Implementation slices

1. Pure in-memory registry and cleanup-tombstone value contract with injected
   handles and no native imports.
2. Binding-aware snapshot provider using injected query functions only.
3. Watcher-owned cleanup transition using injected cleanup functions only.
4. Lazy explicit Windows function binding, fake-only qualification first.
5. Separately authorized bounded native qualification. No native call is
   inferred from completion of slices 1 through 4.

Each slice gets focused, complete EA-4E.92S, canonical guarded Hermes Core,
staged-export and committed-tree verification before the next slice.

## Prohibited shortcuts

- reopening by PID/TID;
- persisting raw handles;
- using the broker's handle integer from `ProbeStart` as watcher authority;
- declaring handles closed from absence alone;
- querying closed handles;
- silently recreating a lost registry;
- cleanup inside the read-only snapshot provider;
- retry/fallback discovery;
- machine-wide process termination;
- weakening schema-v2 binding validation.

## Exit state

- Design frozen: yes.
- Production/test code changed: no.
- Native provider implemented: no.
- Native API/process/resource operation: zero.
- Machine mutation: zero.
- Production activated: no.
- Receiver/model invoked: no.

Next boundary: EA-4E.92Y pure retained-handle registry and immutable cleanup-
tombstone implementation, fake-only and non-live.
