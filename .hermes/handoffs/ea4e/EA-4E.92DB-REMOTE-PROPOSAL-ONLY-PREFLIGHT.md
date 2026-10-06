# EA-4E.92DB remote proposal-only preflight

Status: NON-LIVE DESIGN / IMPLEMENTATION HOLD
Baseline: `61d0157abfd147cdc6059acc4d0156fe7251f377`

## Boundary

The current PC is an untrusted submission client under the administrator-in-scope
decision in 92CZ. The existing `POST /api/governed-production-action` path is
not a remote submission API: it accepts caller-supplied activation intent and
governance artifacts and can reach an issuer when configured. It remains
unchanged and default-disabled. This checkpoint authorizes no route, process,
receiver, provider, model, or production activation.

The proposed remote intake accepts only an inert task proposal. A successful
receipt means `PENDING_REVIEW`, never `AUTHORIZED`, `EXECUTING`, or a promise
that work will run. The remote execution host must own the issuer, durable
stores, receiver, gateway, credentials, audit, and cleanup. A credential or
approval click controlled solely by this PC is not independent approval.

## Candidate proposal contract, not yet frozen

- Required: protocol version, client-generated idempotency key, requested
  receiver identity, canonical task bytes, and their digest.
- The remote host computes its own digest over received canonical bytes and
  rejects a mismatch, unknown version, unsupported receiver, oversized task,
  malformed encoding, or conflicting reuse of an idempotency key.
- A repeated identical submission may return the same inert receipt; the
  same key with different bytes must deny. Neither case may issue or consume
  authority. The remote host assigns its own receipt ID and records the
  proposal in a store separate from authorization and attempt stores.
- Client-claimed source identity is untrusted metadata. The remote host must
  bind any trusted source identity using its own authentication policy.
- Proposal input must not contain execution authority, issue request,
  activation artifact, binding handle, credential, model route override,
  launch arguments, runtime path, or claimed approval verdict.
- A separate remote-side operator action, authenticated independently of
  this PC, must bind approval to the exact proposal digest, trusted source,
  receiver, model route, scope, TTL, one-attempt budget, and cancellation
  state before issuance can be considered. Submission alone never calls
  issuer, binding controller, executor, gateway, or model.

## Qualification before implementation

1. Name the independent host administrator, host class, trusted deployment
   path, operator approval channel, audit owner, and rollback owner. None is
   selected or provisioned here.
2. Freeze canonical serialization, size ceiling, idempotency namespace,
   authenticated source identity, retention, and cancellation semantics.
3. Build an isolated fake intake and tests proving submission-only effects:
   malformed, replayed, conflicting, stale, and cancelled proposals cannot
   mutate authorization, attempt, binding, or execution state.
4. Prove a remote-side approval is necessary and sufficient only for the
   *next governed decision*, not for automatic execution. Test an elevated
   client adversary against the deployed host under separate authorization.
5. Independently resolve the exact 92AT mapped-image-byte proof. Remote
   intake, file hashes, and fake tests do not satisfy that invariant.

## Current disposition

`REMOTE_AUTHORITY_OWNER_FROZEN=NO`
`REMOTE_OPERATOR_APPROVAL_CHANNEL_FROZEN=NO`
`REMOTE_PROPOSAL_CONTRACT_FROZEN=NO`
`REMOTE_SUBMISSION_IMPLEMENTED=NO`
`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`
`PRODUCTION_READY=NO`
`LIVE_ACTIVITY=0`

This is a next-step contract draft, not an approval to expose the local app
or run a real receiver. The next decision requires the independent host and
approval owner; do not substitute a local account, VM, or API key on this PC.
