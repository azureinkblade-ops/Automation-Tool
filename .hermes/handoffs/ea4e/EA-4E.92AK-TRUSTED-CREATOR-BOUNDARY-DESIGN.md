# EA-4E.92AK Trusted Creator Boundary Design

## Disposition

NON-LIVE DESIGN ONLY. The synchronized baseline is
`4e035ee51c7be1ae30caf6e3530e5c6d517d1b05`. No native adapter,
process creation, resume, receiver call, model call, or production activation
is authorized by this document. The 7.7.9 source pin is not receiver proof.

## Problem

EA-4E.92AE validates a caller-constructed creation receipt. EA-4E.92AF
checks three independent containment observations but explicitly returns an
untrusted result. Neither proves that a reviewed native adapter called
`CreateProcessW` with `CREATE_SUSPENDED`, nor can either grant resume.
EA-4E.92AD replaces only the unavailable independent suspended-thread query;
all other containment and cleanup requirements remain in force.

## Proposed ownership boundary

1. A reviewed creator fixes the creation flags and job/AppContainer attributes
   in its own native call. Its caller cannot supply a `suspended` Boolean,
   creator identity, raw handles, or a positive receipt.
2. On successful creation, the creator retains the exact process/thread
   handles and creation attributes in one lifecycle owner. It emits an
   in-memory receipt bound to the request, reviewed adapter hash, job,
   process/thread handles and IDs, and owner identity. A hash string alone
   is metadata, not proof of which code actually executed.
3. The same owner serializes observation, denial cleanup, and any later
   resume. It cannot transfer or duplicate the primary-thread handle.
   Unexpected owner state, handle drift, cancellation, or cleanup ambiguity
   is sticky unknown and denies resume without automatic retry.
4. Before a positive pre-resume verdict, the owner checks exact process/job
   membership, active count one, AppContainer SID, process/thread identities,
   creation flags and still-owned attributes. The verdict must explicitly
   cite trusted creation provenance, not a measured suspend count.
5. A separately reviewed one-shot resume operation may consume that verdict
   only for the same owner and request. Replay, concurrent attempt, changed
   identity, denial, unknown state, or cleanup all prevent the resume call.
   A fake receipt or `UntrustedCreationObservation` can never be upgraded to
   this verdict by a caller-supplied assertion.

## Implementation slices and gates

- First, specify the creator/owner state transitions and fake-only contract
  tests. Preserve the old verifier and its tests until the replacement is
  independently qualified. Fake collaborators may prove ordering and denial,
  but their positive path is not native or production qualification.
- Then implement and review the native creator behind an explicit, narrow
  authorization. Freeze exact adapter source/hash, host, runtime, profile,
  executable/argv, job and token identities, and a bounded fixture before any
  native probe. Those values are **not yet frozen** here.
- Require exact-handle cleanup, creation-flag drift, cross-request/owner,
  replay, concurrency, cancellation, and query-failure tests. Compare the
  full guarded Hermes Core failure identities to the committed 92AJ baseline;
  its 35 inherited failures remain open, not a green gate.
- Run staged-export and committed-tree gates before claiming a checkpoint.
  Source-only qualification does not authorize receiver execution or
  production activation.

## Current state

`NATIVE_EXECUTION_HOLD=YES`; `TRUSTED_CREATOR_IMPLEMENTED=NO`;
`POSITIVE_RESUME_AUTHORITY=NO`; `RECEIVER_QUALIFIED=NO`;
`PRODUCTION_ACTIVATED=NO`.
