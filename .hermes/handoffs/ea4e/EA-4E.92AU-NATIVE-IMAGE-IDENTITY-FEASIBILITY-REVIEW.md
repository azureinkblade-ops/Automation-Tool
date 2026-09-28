# EA-4E.92AU Native Image-Identity Feasibility Review

## Disposition

NON-LIVE SOURCE/API REVIEW at synchronized 92AT commit
`0340f8806154a31701ee951d0ae7f3dd42ae901f`. No production or test
source change, host-path inspection, native API call, process creation,
fixture execution, thread resume, receiver/model invocation, GPU/ComfyUI
use, or production activation is authorized by this review.

`PATH_INSPECTION_DESIGN=PARTIAL`

`POST_CREATION_IMAGE_FILE_ID_PROOF=UNRESOLVED`

`TRUSTED_CREATOR_IMPLEMENTATION=HOLD`

`NATIVE_PROBES_AUTHORIZED=NO`

## Evidence Found

- The repo's `ea4e92s_windows_profile.py` uses `CreateFileW` and
  `GetFileInformationByHandleEx` to inspect one existing profile directory.
  It does not inspect runtime/bootstrap/request paths or every ancestor.
- `ea4e92s_creator_preflight.py` accepts injected `PathSnapshot` objects;
  it does not open a file, hash bytes through a retained handle, or prove
  that a later path-based creation mapped the same executable.
- Repository search found no process-image file-ID query adapter. The
  existing pre-resume verifier checks job membership/count, SID, and a
  caller-supplied suspended-thread predicate, not executable file identity.
- Microsoft documents `FILE_ID_INFO` as file identity from a **file
  handle**. `QueryFullProcessImageNameW` returns the process image **name**.
  The reviewed documentation does not establish that this process pathname
  equals the exact pre-inspected file ID or bytes after a path-based
  `CreateProcessW` call. This is a gap in reviewed proof, not a universal
  claim that no such Windows mechanism exists.
- `FILE_FLAG_OPEN_REPARSE_POINT` can prevent following a reparse point on
  the opened object. The reviewed documents do not by themselves prove
  that an absolute-path `CreateFileW` call has safely validated every
  traversed ancestor against replacement or redirection.

## Consequence for EA-4E.92AT

92AT requires a post-creation, pre-resume binding to the reviewed runtime
file, not merely a matching pathname. It also requires no-reparse parent
traversal and owned handles retained across the one-shot creation attempt.
Implementing a five-path inspector with `CreateFileW` and `FILE_ID_INFO`
would prove properties of the objects opened by that inspector, but would
not alone close the gap between those handles and the executable image
that a later path-based process creation actually mapped. No positive
trusted receipt may be issued from that partial result.

## Narrow Next Qualification Work

1. Identify a supported, reviewable method to bind the suspended process's
   mapped executable to the pre-inspected file ID/bytes, **or** define an
   independently reviewable immutable staging/ACL/handle regime that
   excludes replacement throughout creation. State the exact threat model
   and residual race; do not quietly substitute a pathname comparison.
2. Specify the component-walk API and exact open/access/share/flag values
   for all five paths, including handle retention and uncertain cleanup.
   Prove parent-component behavior rather than assuming final-component
   reparse flags cover it.
3. Independently review the resulting source/API contract. Only after that
   review may a non-live native-inspector implementation with fake-injected
   APIs and fail-closed tests be proposed. No live probe follows from a
   source-only implementation.
4. Separately, the fake-only one-owner state machine can be implemented and
   tested without a native image verdict. It must never make `VERIFIED`
   reachable through a caller-supplied Boolean, path string, or fake receipt.

If item 1 remains unproven, the creator's positive path remains blocked.
The project may still qualify denial, cleanup, and accounting in fake-only
tests, but cannot claim native containment or production readiness.

## References

- [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)
- [QueryFullProcessImageNameW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew)
- [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)
- [GetFileInformationByHandleEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex)
- [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)

## Exit State

`EA4E92AU_REVIEW_COMPLETE=YES`

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`NATIVE_INSPECTOR_IMPLEMENTED=NO`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`
