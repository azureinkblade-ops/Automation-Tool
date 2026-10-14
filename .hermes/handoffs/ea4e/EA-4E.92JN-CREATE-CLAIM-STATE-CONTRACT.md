# EA-4E.92JN create-claim state contract

Status: NON-LIVE DESIGN / NO DOCKER MUTATION OR ISSUANCE AUTHORIZED.
Governing source: `64f8672532c0a062e40943615e88acfd0f5707cc`.

## Identity and ownership

The claim belongs in the same SQLite authority database as the reserved
Kilo intent and created-container report. Its primary key is the existing
`attempt_id`; the create authorization ID is unique separately. The sealed
payload binds the intent hash, candidate/spec/request hashes, exact image
index and manifest, Docker executable hash and engine endpoint, deterministic
network/container names, network/gateway ownership records, mount-source
hashes, source commit, TTL, and one-shot authorization ID. A caller-supplied
ID or hash is never evidence that an authorization was issued. The issuer
and its verification contract require a separate design and approval.

The claim must be inserted in a `BEGIN IMMEDIATE` transaction only after
current authority, cancellation, revocation, expiry, source bytes, and the
exact authorization are checked in the same governing transaction. A
preexisting claim, even one with identical bytes, cannot grant another
mutation. Read-only replay may report the existing state and identity.

## One-shot transitions

`CLAIMED` means a mutation budget was durably consumed, not that Docker
acted. Before invoking Docker, the owner durably advances to `IN_FLIGHT`.
There is no transition from either state back to a fresh claim. A proven
single created ID can advance to `CREATED_REPORTED` after raw evidence is
saved. Any timeout, crash, lost acknowledgement, ambiguous output, or
unexpected object advances to `UNKNOWN_CREATE` or remains `IN_FLIGHT` on
crash; both deny automatic retry. Cancellation/revocation can only tighten
the state. A created report does not authorize `start`.

On restart, `CLAIMED` is also conservatively treated as potentially used:
there is no automatic create attempt. A read-only reconciler may inspect
the exact deterministic name, labels, network, and image under the original
claim. Zero or multiple candidates, changed identity, or missing raw
evidence remain HOLD. A single match can be recorded for operator review
and 92IJ/92JK prestart comparison, but cannot replenish the create budget.

## Prerequisites before implementation

- Freeze a separately governed exact create-authorization artifact and
  issuer, including source SHA, attempt, object identities, TTL, operator,
  cancellation/revocation, and audit trail. It must exclude `start`.
- Resolve network and gateway ownership as separate one-shot budgets. A
  preexisting arbitrary object is not an acceptable shortcut.
- Qualify a process-tree-contained mutation driver and post-create
  effective-daemon checks. The current inspect runner kills only its
  immediate CLI child and is not a mutation driver.
- Fake-test concurrent claims, byte drift, expired/revoked authority,
  crash before/after send, timeout after creation, ambiguous name lookup,
  and restart reconciliation against an isolated SQLite database.

No claim store or issuer is implemented by this design. No Docker object
was created, started, or removed. Real create-only qualification needs a
new exact one-shot live authorization; production remains HOLD.
