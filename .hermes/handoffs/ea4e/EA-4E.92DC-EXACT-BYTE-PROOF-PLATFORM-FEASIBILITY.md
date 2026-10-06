# EA-4E.92DC exact-byte proof platform feasibility

Status: SOURCE-ONLY / NO POSITIVE PROOF / NO PLATFORM SELECTION
Baseline: `27b91542e05d309ef5b5a6dbff9e24133767898f`

The operator retained the exact 92AT requirement. This review does not
replace it with App Control PE hash, file identity, later file hash, or a
process-memory digest. It follows the independent 92BA REJECT disposition
and the administrator-inclusive 92CZ threat model.

## Windows candidate

Microsoft documents that executable images are loaded through an image
section and that the backing file need not remain open. The process creation
debug event may provide an `hFile` for the image file, but it may be null and
the event does not report a digest of the created section's source bytes.
`CreateFileMapping` can create a separate `SEC_IMAGE` mapping from a supplied
file handle; this does not attest that a `CreateProcessW` child used that
mapping. These are observations about documented interfaces, not a proof
that no other Windows mechanism could ever satisfy 92AT. The exact positive
proof is still unavailable in the reviewed design.

Windows references:

- https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/executable-images
- https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info
- https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw

## Separately administered Linux candidate

Linux `execveat(fd, "", ..., AT_EMPTY_PATH)` executes the file referred to
by an open descriptor. `memfd_create(MFD_ALLOW_SEALING)` permits a file to be
populated and sealed against later modification. Together they suggest a
possible handle-bound executable provenance design, but this is an inference,
not a qualified exact image-byte attestation. It requires a separate review
of ELF interpreter, dynamic libraries, script behavior, seals, descriptor
inheritance, namespace isolation, and privileged host administrators. The
frozen 92AT Windows suspended-process and AppContainer contract cannot be
silently reinterpreted as Linux `execveat`.

Linux references:

- https://man7.org/linux/man-pages/man2/execveat.2.html
- https://man7.org/linux/man-pages/man2/memfd_create.2.html

## Decision gate

The operator confirmed on 2026-10-06 that no separately administered host
is available yet. No host OS or independent operator approval channel has
been selected.
If the selected host is Windows, require new authoritative evidence for the
exact created-section-to-reviewed-bytes relation before positive creator
qualification. If it is Linux, authorize a separately versioned execution
contract and independent proof review before implementation. In either
case, remote proposal intake remains inert and cannot issue or execute.

`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`LINUX_ALTERNATIVE_QUALIFIED=NO`
`REMOTE_HOST_SELECTED=NO`
`PRODUCTION_READY=NO`
`LIVE_ACTIVITY=0`
