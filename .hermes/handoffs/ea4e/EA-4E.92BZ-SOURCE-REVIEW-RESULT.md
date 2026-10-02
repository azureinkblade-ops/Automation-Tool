# EA-4E.92BZ Exact Image-Section Byte-Proof Source Review

## Scope and verdict

Source-only review of the EA-4E.92BZ request against the frozen EA-4E.92AT
requirement and primary Microsoft documentation. This is this project's own
technical review, not an independent platform certification. It does not
change the user decision to retain the exact raw-byte invariant.

`EXACT_INVARIANT=INSUFFICIENT_EVIDENCE`

`CURRENT_FILE_ID_PLUS_SHA256_POSITIVE_RECEIPT=REJECT`

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`TRUSTED_NATIVE_CREATOR=HOLD`

`PRODUCTION_ACTIVATED=NO`

The supported API set reviewed here does not provide a chain from the
reviewed raw-file bytes to the particular image section used by one
`CreateProcessW` result. This is a limit of the reviewed evidence, not a
proof that no possible Windows mechanism exists.

## Evidence chain

| Candidate | Documented fact | Missing link |
| --- | --- | --- |
| Retained file handle and `CreateProcessW` | `lpApplicationName` names a module; the API has no input for the retained executable file or section handle. | The prior hash/handle cannot itself select the loader's image section. |
| Create-process debug event | `hFile` is an image-file handle and can be null. `lpBaseOfImage` is an address. | Neither field is a section handle, source-byte digest, or always-present attestation. |
| `FILE_ID_INFO` | Volume serial plus file ID compares whether two open handles represent the same file. | Same file is not same stream state at section creation or proof of section source bytes. |
| Kernel process notification | `PS_CREATE_NOTIFY_INFO.FileObject` identifies the process executable file object, subject to documented null cases. | File-object identity still does not expose the mapped section's source bytes. |
| File stream's section pointers | `SECTION_OBJECT_POINTERS.ImageSectionObject` links a stream to an opaque image-section control area; its value can change. | The documentation instructs filters to treat it as opaque and exposes no cryptographic byte measurement for the created process. |
| Section-synchronization callback | The file system can observe a section-create request and its protection/synchronization type. | The documented callback parameters do not attest which raw bytes the eventual process image section represents. |
| Explicit section from retained file handle | `ZwCreateSection`/`NtCreateSection` can create a section backed by the specified file handle. | The frozen `CreateProcessW` call cannot be passed that section handle; creating our own section does not prove the loader used it. |
| `SEC_IMAGE` mapping or process-memory hash | An image mapping follows PE layout and protection rules, not a raw-file byte-for-byte view. | A hash of mapped memory is not the previously reviewed raw-file SHA-256 or a documented source-byte attestation. |
| Authenticode/App Control PE hash | The documented PE image hash excludes certain ranges, including certificate-related data. | It is a distinct measurement and the user explicitly rejected it as a substitute for the raw-byte invariant. |

Fresh private-file staging and write exclusion may support a constrained
file-provenance claim under the 92BA threat model. They do not supply the
missing loader-attested section-source-byte observation. A pre-existing
image section for a non-fresh runtime file is an additional reason a later
file read cannot automatically describe the section. A successful host
experiment would show behavior on that host/build, not create the absent
documented contract.

## Decision boundary

No current candidate may mint `VERIFIED_SUSPENDED`; do not implement a
positive creator, run a native probe, or infer production readiness from
fake tests. An exact-positive result would require a reviewed and
supportable OS guarantee or API binding the created process's specific
image section to the reviewed source bytes, with lifetime and race analysis
for the target Windows builds. A different process-creation mechanism or
kernel component would be a versioned architecture change, not an implicit
fix to the frozen `CreateProcessW` plan. The user's rejected weaker PE-hash
or file-provenance contract is not reopened by this review.

EA-4E.92AY Q1/Q3/Q4 and 92BA write-exclusion/namespace questions also
remain open. Even a future byte-proof resolution would not by itself
authorize receiver/model execution or production activation.

## Primary sources

- `CreateProcessW`: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw
- `CREATE_PROCESS_DEBUG_INFO`: https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info
- `FILE_ID_INFO`: https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info
- `PS_CREATE_NOTIFY_INFO`: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-_ps_create_notify_info
- `SECTION_OBJECT_POINTERS`: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ns-wdm-_section_object_pointers
- Section-synchronization parameters: https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/flt-parameters-for-irp-mj-acquire-for-section-synchronization
- `ZwCreateSection`: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-zwcreatesection
- `CreateFileMappingW` `SEC_IMAGE`: https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw
- Executable images: https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/executable-images
- PE hash exclusions: https://learn.microsoft.com/en-us/windows/win32/debug/pe-format

No production or test source was changed; no native process, receiver,
model, provider, GPU/ComfyUI, or production operation was invoked.
