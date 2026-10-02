# EA-4E.92BZ Exact Image-Section Byte-Proof Review Request

## Status and authority

NON-LIVE REVIEW REQUEST ONLY. EA-4E.92AT retains its exact image-section
byte-binding requirement. EA-4E.92BA independently rejected the available
user-mode evidence for that requirement. This packet neither revises the
contract nor authorizes native process creation, receiver/model execution,
GPU/ComfyUI use, or production activation. The default verdict remains HOLD.

## Question for an independent Windows loader/filesystem reviewer

On the target supported Windows builds, is there a documented, supportable
mechanism by which the creator can attest that the specific executable image
section used for its one `CreateProcessW` attempt represents the exact raw
bytes of the independently reviewed executable? The proof must bind the
created process and its section to those bytes before any thread is resumed.

A positive answer must identify the exact API or OS guarantee, the objects
and handles it binds, when that evidence becomes available, the required
privilege and deployment model, and how it excludes a pre-existing section,
replacement/reparse/namespace race, and post-hash mutation. It must explain
the relation between raw-file bytes and PE image mapping. If the answer
requires a kernel driver or a different process-creation contract, say so
explicitly; do not treat that as an already-authorized implementation.

## Candidate evidence to evaluate, not assumed solutions

1. `CreateProcessW` consumes an executable path, not the retained reviewed
   file handle. A process-create debug event can expose an image-file handle,
   but it may be null and is not an image-section digest. Determine whether
   any documented additional observation closes that specific gap.
2. A process-creation notification supplies a `FileObject` for the process
   executable (except documented null cases). Determine whether it attests
   section source bytes, or only file-object identity. The latter is
   insufficient for the frozen requirement.
3. A filesystem section-synchronization callback can observe a section-create
   request. Determine whether it can provide an exact, race-free relation
   between the resulting image section and previously reviewed raw bytes.
   The documented callback parameters alone do not expose such a digest.
4. Authenticode or App Control PE hashes omit some raw-file ranges. The user
   has explicitly declined treating those measurements as equivalent to the
   frozen raw-byte invariant. Evaluate them only as distinct alternatives,
   not as a positive answer to this request.

## Required review result

Return one of `SUPPORTED`, `UNSUPPORTED`, or `INSUFFICIENT_EVIDENCE` for the
exact invariant. `SUPPORTED` requires primary Microsoft documentation or an
equally authoritative platform contract for every critical link, plus a
threat-model and lifetime analysis. Empirical host behavior alone is not a
portable contract. A source-only sketch, file-ID equality, later file hash,
process-memory hash, fake test, or PE-signature verification cannot mint
`VERIFIED_SUSPENDED`.

If no supportable mechanism is found, state the narrowest demonstrable claim
separately and leave trusted creation on HOLD. Do not silently substitute that
claim for 92AT. If a materially different architecture is needed, identify
its new authority, deployment, and regression boundaries before any code or
live qualification is proposed.

## Governing local evidence

- `EA-4E.92AT-NATIVE-IDENTITY-AND-CREATOR-OWNER-DESIGN.md`: exact creator
  state machine and pre-resume image-binding requirement.
- `EA-4E.92AY-INDEPENDENT-WINDOWS-IDENTITY-REVIEW.md`: independent Windows
  identity and debug-path review.
- `EA-4E.92AZ-MAPPED-IMAGE-PROOF-OPTIONS-REVIEW.md`: options and contract
  impact.
- `EA-4E.92BA-INDEPENDENT-STAGING-PROOF-REVIEW.md`: fresh staging helps
  provenance but does not establish the section-source-byte invariant.

## Primary platform references to examine

- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw
- https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info
- https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-_ps_create_notify_info
- https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/flt-parameters-for-irp-mj-acquire-for-section-synchronization
- https://learn.microsoft.com/en-us/windows/win32/debug/pe-format

No new proof or host behavior is claimed by this packet. Until an independent
review supplies a supported positive result and the necessary contract rolls
are separately authorized, `TRUSTED_IMAGE_BINDING_QUALIFIED=NO`.
