# EA-4E.92BD Exact Image-Byte Proof Escalation

## Status and Scope

Non-live research and escalation packet only. Governing source commit:
`bfdbf6243d5f938606840fc6e2ca9a459c3af607`. The 92BB decision
retains the exact 92AT post-create, pre-resume mapped-image byte
requirement. This packet neither relaxes that requirement nor qualifies
trusted creation. No process, receiver, model, driver, GPU, or ComfyUI
activity is authorized here.

## Exact Question for a Windows Loader Reviewer

For a Windows process created from a named PE executable with
`CreateProcessW` and still suspended before its first thread resumes,
is there a **documented, supported** API or enforced construction that
establishes that this process's particular executable image section was
constructed from exactly the bytes of a previously SHA-256-reviewed file
stream? The answer must identify:

1. The object whose bytes are measured: raw stream, image section at
   creation, or mapped process view. State whether the measurement covers
   all raw bytes or only PE image bytes.
2. The exact process-to-section and section-to-stream binding, including
   what object/handle/identifier carries each binding.
3. Whether a previously existing image section can be reused, and how
   fresh staging or explicit section creation changes that answer.
4. How file mutation, alternate streams, reparse/volume namespace changes,
   copy-on-write, relocations, imports, zero-fill, and demand paging affect
   the claimed equality.
5. The supported observation or enforcement point before resume, its
   failure cases, and the Windows versions on which it is guaranteed.
6. Whether the supported process-creation API can consume an already
   reviewed **section handle or file handle** rather than resolve a path.

A positive answer needs primary Microsoft documentation or a qualified
loader/filesystem review tied to a precise Windows build and threat model.
A file ID, image path, later file hash, Authenticode/PE hash, or selected
memory-page comparison alone is not an answer to this question.

## Research Already Excluded

- `CreateProcessW` accepts an executable name, not an executable file or
  image-section handle. The experimental sandboxed equivalent likewise
  accepts `applicationName` and `commandLine`, not a section handle.
- `ReadProcessMemory` copies readable address-space bytes at observation
  time. It does not report the source bytes from which the section was
  constructed. `VirtualQueryEx` can report `MEM_IMAGE` even after an
  image page becomes private by copy-on-write.
- The PE file's raw offsets and lengths differ from loaded virtual layout;
  zero-fill, relocations, and import fixups prevent a flat-file SHA-256
  from being compared directly with loaded memory. WinDbg `!chkimg`
  deliberately excludes several sections and the import address table.
- The documented image-load and process-create kernel callbacks expose
  file objects or opaque section state, not an attested section-source
  byte digest. `ZwCreateSection` can create a section from a file handle,
  but the reviewed `CreateProcessW` API does not take that section handle.

These are scoped findings about reviewed documented interfaces, **not**
a claim that no possible Windows mechanism exists.

## Decision Gate

Until the exact question above is answered and independently reviewed,
`MAPPED_BYTE_INVARIANT=REJECT_ON_AVAILABLE_EVIDENCE` and
`TRUSTED_NATIVE_CREATOR=HOLD`. Do not substitute a weaker provenance
claim or implement a positive `VERIFIED_SUSPENDED` result. If no supported
method can be identified, the existing 92BB architecture decision remains
the stopping point; a different contract requires a new explicit user
decision.

## Primary References

- [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)
- [Experimental CreateProcessInSandbox](https://learn.microsoft.com/en-us/windows/win32/secauthz/createprocessinsandbox)
- [ReadProcessMemory](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-readprocessmemory)
- [VirtualQueryEx](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualqueryex)
- [PE format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)
- [WinDbg !chkimg](https://learn.microsoft.com/en-us/windows-hardware/drivers/debuggercmds/-chkimg)
- [Executable images](https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/executable-images)
- [ZwCreateSection](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-zwcreatesection)
- [EA-4E.92BA independent review](EA-4E.92BA-INDEPENDENT-STAGING-PROOF-REVIEW.md)
- [EA-4E.92BB architecture decision](EA-4E.92BB-RETAIN-EXACT-MAPPED-BYTE-REQUIREMENT.md)
- [EA-4E.92BC kernel review](EA-4E.92BC-KERNEL-IMAGE-OBSERVATION-FEASIBILITY-REVIEW.md)
