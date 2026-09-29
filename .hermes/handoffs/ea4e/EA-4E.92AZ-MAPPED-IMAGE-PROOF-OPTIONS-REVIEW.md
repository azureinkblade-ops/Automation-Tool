# EA-4E.92AZ Mapped-Image Proof Options Review

## Boundary

NON-LIVE DESIGN REVIEW at `cd0763f9f0469a8b2123b62778ecc0b63831dfb3`.
The independent 92AY result is Q1 HOLD, Q2 REJECT, Q3 HOLD, Q4 HOLD,
overall HOLD. This review changes no production/test source and grants no
host-path inspection, native API call, process attempt, fixture, receiver,
model, GPU/ComfyUI, or production activation.

## Exact Question

92AT requires the still-suspended process image to be independently bound
to the reviewed runtime identity before `VERIFIED_SUSPENDED`. 92AY rejected
the proposed inference that matching `FILE_ID_INFO` on a debug-event
`hFile` and a retained file handle, plus SHA-256 of that file, proves the
bytes in the executable image section. The decision here is whether a
supported, reviewable source-only contract can close that gap without
weakening 92AT's claim.

## Documentation-Backed Limits

- [`CreateProcessW`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)
  accepts `lpApplicationName` as a name, not a retained executable file
  handle. A pre-opened file handle does not itself bind that path lookup.
- [Executable Images](https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/executable-images)
  describes executable loading through a memory-mapped image section;
  the file need not remain open. A later file read is not documented as a
  read of the section's original image bytes.
- [`FILE_ID_INFO`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)
  supports comparing two file handles' volume serial and file ID. It
  establishes same-file identity on a single computer, not mapped-image
  content or alternate-stream identity.
- [`CREATE_PROCESS_DEBUG_INFO`](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info)
  exposes an image-file `hFile` that may be null. It does not expose the
  image section's source bytes or a loader-attested digest.
- [Creating a File Mapping Object](https://learn.microsoft.com/en-us/windows/win32/memory/creating-a-file-mapping-object)
  recommends exclusive file access to prevent other writers to a mapping.
  It does not claim that a hash of a file handle attests the image section
  used by a separately created process.

## Candidate A: Private Fresh-File Staging

This is an investigation candidate, **not** a qualified implementation.
Create a new per-attempt file object under a private, reviewed directory;
write only approved bytes; hash through its owned handle; deny sharing
that permits later write or delete; retain owners through creation; and
compare the debug event's file ID to the staged file ID before any resume.
[`CREATE_NEW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
can reject an existing name, and a creation-time security descriptor can
restrict later opens. Those are ingredients, not the missing proof.

Unresolved obligations before any positive verdict:

1. Prove the exact per-attempt file was newly created and could not have
   a pre-existing image or writable section. Specify directory/file ACLs,
   owner token, hard-link and alternate-stream policy, and threat limits.
2. Prove no writer or namespace substitution can intervene between the
   approved write/hash, staged-path lookup by `CreateProcessW`, and image
   section creation. Specify exact access/share modes and retained handles.
3. Prove the event `hFile` identifies the loader's section source and that
   the section represents the approved staged bytes. File-ID equality
   alone does not prove this last implication.
4. Specify how staging affects the frozen runtime path/file-ID pins,
   launch argv, cleanup, cancellation, and one-attempt accounting. A copy
   is a new file identity, so the current exact contract cannot be reused
   silently.
5. Resolve 92AY Q1/Q3/Q4 separately. Staging does not qualify debug
   handle availability, five-path traversal, or debugger lifecycle.

Because obligations 2-3 are not established by the reviewed docs,
`PRIVATE_STAGING_MAPPED_IMAGE_PROOF=HOLD`. A fake test of this plan would
only show that the *policy code* denies bad inputs; it cannot prove the
Windows loader's byte-level behavior.

## Candidate B: Weaker Security Claim

A separately governed architecture change could ask whether the actual
production requirement is file-object provenance plus containment, rather
than exact mapped-byte equivalence. That is **not** an interpretation of
92AT and is not authorized here. It needs an explicit threat-model and
contract decision, independent security review, and a new qualification
program. It cannot be accomplished by renaming `VERIFIED_SUSPENDED` or
relaxing an equality check.

## Disposition and Next Decision

No reviewed, supported user-mode route currently closes the 92AT
mapped-byte invariant. Do not implement a positive native creator or a
four-flag debug roll on this evidence. The next bounded non-live action is
an independent Windows loader/filesystem security review of Candidate A's
five obligations, with an explicit decision on whether the byte invariant
is provable under a restricted local threat model. If not, governance must
decide whether to retain the HOLD or authorize a different security claim
under Candidate B. No live probe follows automatically from either review.

`EA4E92AZ_SOURCE_REVIEW=COMPLETE`

`PRIVATE_STAGING_MAPPED_IMAGE_PROOF=HOLD`

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`TRUSTED_NATIVE_CREATOR=HOLD`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`
