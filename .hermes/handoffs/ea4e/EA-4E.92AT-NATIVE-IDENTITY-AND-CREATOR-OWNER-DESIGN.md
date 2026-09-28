# EA-4E.92AT Native Identity and Creator-Owner Design

## Disposition

NON-LIVE DESIGN ONLY at synchronized commit
`0484877ce7fcd3446b5399acb27a535660330f4c`. This document grants no
native API binding, path inspection on the host, process creation, Node
fixture execution, thread resume, receiver/model activity, GPU/ComfyUI use,
or production activation. The guarded broad suite still has 35 inherited
failures. EA-4E.92AS compares injected snapshots and prepares a value-only
call plan; it is not a trusted creator or native identity proof.

## Boundary to Implement Next

One reviewed Windows inspector must produce evidence for the exact five
92AS paths: runtime executable, bootstrap, request artifact, request root,
and existing AppContainer profile directory. It must not issue pins itself;
the caller supplies independently reviewed path, volume/file ID, byte size,
and SHA-256 values where applicable. The inspector never changes a profile,
ACL, file, or process and never follows an unreviewed fallback path.

For each path, the native implementation must validate every traversed
component against reparse-point redirection, then open the final object
without silently following a final reparse point. It must query final-object
attributes and volume/file ID from an owned handle. Files require size and
SHA-256 over bytes read through that same handle; directories require their
reviewed directory identity and no-reparse status. An open failure, short
read, identity/hash mismatch, unknown component, sharing conflict, or
uncertain handle cleanup denies; no retry or alternate open mode is allowed.
The exact access/share/flag values and component-walk method need a separate
source review before implementation. Merely checking a string path or final
component is insufficient.

The inspector returns an owned handle set plus immutable snapshots. The
creator must retain these owners across a single native creation attempt or
fail closed. Retention narrows replacement races but does **not** prove that
a path-based process-creation call mapped the inspected executable. The
creator must therefore independently verify the newly created, still
suspended process image against the reviewed runtime identity before any
resume. A reported image pathname alone is metadata, not proof of byte or
file identity. If the available Windows APIs cannot establish that binding
to the reviewed file, the native qualification remains HOLD; do not promote
a best-effort comparison to a trusted creation receipt.

## Single Owner and State Machine

The creator accepts only the exact 92AS call plan, the still-owned native
inspection handles, the reviewed job/SID/attribute owners, and one bounded
request. It fixes the flags, null security attributes, and handle-inheritance
policy itself; the caller cannot provide a `suspended` Boolean, raw output
handles, positive receipt, or alternate launch arguments. Process and thread
handles returned by creation enter the same owner immediately, including on
partial success or an ambiguous return. No path in this design performs a
launch; this is the required shape for a later implementation.

State transitions are one-way:

1. `PREPARED`: all exact pins and owners still valid; no call made.
2. `CALL_IN_PROGRESS`: one attempt consumed before entering the native call.
3. `SUSPENDED_OWNED`: one returned process/thread pair retained; no resume.
4. `VERIFIED_SUSPENDED`: image identity, job membership/count, AppContainer
   SID, process/thread IDs, and unchanged owners independently verified.
5. `TERMINATING` -> `CLOSED`: exact owned process/job termination and handle
   cleanup confirmed.
6. Any ambiguous call, observation, cancellation, or cleanup goes to sticky
   `UNKNOWN`; no automatic retry, new attempt, or resume.

The earlier fake lifecycle and caller-constructed creation receipt remain
untrusted and must not be converted into `VERIFIED_SUSPENDED` by assertion.
NQ-01 may terminate without resume only under a separate exact live
authorization. Any later one-shot resume is a different governed boundary.

## Required Source-Only Qualification Before a Live Request

- Fake-only tests cover five-path pin/snapshot mismatch, each parent and
  final-component reparse, changed file ID/volume/hash/size, cross-request
  owner, closed handle, cleanup failure, and path substitution.
- A recording fake checks exact native-call arguments, `CALL_IN_PROGRESS`
  accounting, returned-handle ownership, partial/ambiguous result, and
  cancellation/concurrency/replay denial without invoking a process API.
- A fake post-creation observer must show that pathname-only evidence cannot
  grant the positive image-identity verdict. Missing identity API support is
  a HOLD, not a relaxed comparison.
- Run focused, bounded, isolated staged-tree, and committed-tree gates.
  Compare broad-suite failure identities to committed 92AS; the 35 inherited
  failures remain visible rather than relabeled green.

## Separate Live-Qualification Gate

Before any NQ-01 or Node parser fixture process, freeze the exact source
commit and native adapter hashes, Windows host/build, current Node executable
path/hash/file ID, bootstrap and request hashes, profile name/binary SID/
storage identity, ACL proof, complete ordered argv/environment, job limits,
one-attempt/one-process budget, timeout/output ceilings, evidence destination,
and exact cleanup/reconciliation owner. Recheck all of them immediately before
the authorized call. The authorization must explicitly permit that one
process attempt. A generic "next stage" instruction or a fake test result
does not authorize it. No receiver/model or production activation is implied.

## Design References

- [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)
- [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [GetFileInformationByHandleEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex)
- [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)
- [QueryFullProcessImageNameW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew)

## Exit State

`EA4E92AT_DESIGN_DRAFTED=YES`

`NATIVE_INSPECTOR_IMPLEMENTED=NO`

`TRUSTED_CREATOR_IMPLEMENTED=NO`

`NATIVE_PROCESSES_STARTED=0`

`POSITIVE_RESUME_AUTHORITY=NO`

`PRODUCTION_ACTIVATED=NO`
