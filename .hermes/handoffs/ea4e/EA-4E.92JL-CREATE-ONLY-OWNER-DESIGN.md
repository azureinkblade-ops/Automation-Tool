# EA-4E.92JL create-only owner design

Status: NON-LIVE DESIGN / NO DOCKER MUTATION AUTHORIZED.
Governing predecessor: `21476fc62d5f1b6d5d397b00223d029c6f8ea1db`.

## Purpose and scope

Qualify exactly one dummy-credential, local-profile Kilo container through
creation and prestart inspection. This is not receiver execution, model
invocation, production activation, or strict 92AT mapped-byte proof. A
separately reviewed and exactly bound authorization is required before any
real Docker network/container creation. Existing 92JC fields
`create_authorized=false` and `launch_authorized=false` remain unchanged.

## Ownership sequence

1. Rebuild and verify the reserved fake attempt, active authority/start
   witness, 92JC candidate/spec hash, prepared mount-source bytes, pinned
   image index/manifest, explicit Linux-engine pipe, and dummy-only
   credential class. Deny cancellation, revocation, expiry, terminal status,
   changed source bytes, or an existing create claim/report.
2. Persist a single durable create claim **before** the first Docker
   mutation, keyed by `attempt_id`, candidate/spec hashes, deterministic
   network/container names, and the exact one-shot authorization identity.
   Claim replay must return the same state; it must never mint a fresh name,
   workspace, network, or attempt.
3. Resolve network and gateway ownership. The owner may use only a
   separately attested preexisting exact network/gateway, or a separately
   claimed create sequence for those objects. An arbitrary existing network
   or gateway is not an acceptable shortcut. Network creation and gateway
   start are distinct mutation budgets and are **not** authorized by this
   design.
4. Once prerequisites are proven, admit a canonical Docker create request
   derived solely from the frozen spec: exact image index/platform, name,
   labels, non-root UID:GID, workdir, entrypoint/argv, environment,
   reviewed bind sources, read-only root, `/work` tmpfs, CPU/memory/pids,
   all capabilities dropped, no-new-privileges, no published ports,
   no auto-remove/restart, and the exact internal network. Deny every
   omitted, extra, or daemon-default-expanded privilege not covered by the
   review.
5. Capture the exact created container ID from the one command attempt.
   Immediately persist the observed ID and attempt outcome. A timeout,
   disconnect, crash, empty output, or uncertain acknowledgement consumes
   the one-shot budget and enters `UNKNOWN_CREATE`; never issue another
   create automatically.
6. Reconcile `UNKNOWN_CREATE` only by read-only exact-name/label and
   network inspection against the original claim. Zero, multiple,
   renamed, or altered candidates remain HOLD for operator review. Never
   infer success solely from a CLI exit status or caller-supplied metadata.
7. On one unambiguous created object, first inspect the exact container ID
   and pinned image index/manifest read-only. Validate the reported
   created/prestart state, derive the network ID, and persist the 92IJ
   record and its raw container/image hashes. Only then run the 92JK
   observer against those recorded IDs, including the exact network.
   A `MATCH` means only `CREATE_SPEC_REVIEW_ONLY_START_DENIED`; no code
   path may translate it into `start` permission.

## Required implementation gates

- A durable claim/attempt schema and replay/unknown-outcome tests.
- A full Docker create-argv and effective-daemon-setting contract; current
  92JC host settings are a proposal, not a qualified mutation request.
- Exact network/gateway ownership and one-shot accounting, including
  crash/restart reconciliation.
- Explicit fail-closed process isolation for the mutation driver and
  read runner. Immediate-child termination alone is not process-tree proof.
- Fake-only tests for mismatched IDs, stale authority, cancellation,
  duplicate claims, timeout after creation, wrong network member, mount
  drift, and every denied extra privilege.
- A separately approved one-shot real create-only envelope bound to the
  committed source SHA, Docker executable/image identities, attempt ID,
  object names, gateway/network identities, no-start rule, exact cleanup
  ownership, and audit location. No standing or blanket approval suffices.

## Stop condition

This design grants no Docker mutation. The next step is non-live durable
claim and create-contract implementation, followed by fake qualification.
Real object creation and receiver start are separate governance boundaries.
Production remains HOLD.
