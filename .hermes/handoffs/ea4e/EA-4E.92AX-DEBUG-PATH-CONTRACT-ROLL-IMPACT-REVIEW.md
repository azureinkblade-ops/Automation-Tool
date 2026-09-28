# EA-4E.92AX Debug and Path Contract-Roll Impact Review

## Disposition

NON-LIVE SOURCE/API REVIEW on synchronized 92AW commit
`26309873807464840c8b25a3215321b2af8ab7db`. No production or test
source changes, host-path inspection, native API call, process creation,
fixture execution, thread resume, receiver/model invocation, GPU/ComfyUI
use, or production activation are authorized by this review.

`DEBUG_IMAGE_HANDLE_APPROACH=PLAUSIBLE_BUT_UNQUALIFIED`

`EXACT_FLAGS_CONTRACT_ROLL_REQUIRED=YES`

`NO_REPARSE_OPEN_CONTRACT=UNRESOLVED`

`TRUSTED_NATIVE_CREATOR=HOLD`

## Existing Source Contract

The 92AW debug-event candidate requires `DEBUG_ONLY_THIS_PROCESS` to
receive the process-create event and its image `hFile`. The committed
launch contract currently sets only `CREATE_SUSPENDED`,
`CREATE_UNICODE_ENVIRONMENT`, and `EXTENDED_STARTUPINFO_PRESENT`:

- `tools/ea4e92s_launch_inputs.py` constructs that exact value.
- `tools/ea4e92s_creator_preflight.py` rejects a changed value.
- `tools/ea4e92s_creation_provenance.py` rejects a receipt with any extra
  bit; this also affects its downstream observer.
- The AE, AF, AP, and AS tests explicitly preserve the current flags.

Adding the debug bit only at the eventual native call would therefore
break provenance: the call, frozen buffers, preflight plan, and receipt
would disagree. A deliberate versioned contract roll with updated denial
tests and affected downstream review is required. Do not relax validation
to an arbitrary superset of bits or fabricate a matching receipt.

The existing `ea4e92s_windows_profile.py` is a test-owned, one-directory
inspector. It opens with share read/write/delete, closes the directory
handle, and does not inspect every ancestor or the other four paths. It
cannot be promoted into the retained five-path identity owner as-is.

Focused, guarded existing-contract verification: 71/71 passed across AE,
AF, AP, and AS; filesystem and fake-only tripwires both reported zero.
This verifies the current source contract, not debug-flag compatibility.
No broad-suite or live qualification is claimed for this review.

## Path-Opening API Review

Microsoft documents `OBJECT_ATTRIBUTES.OBJ_DONT_REPARSE` as rejecting
reparse points encountered while parsing an object name, and documents
directory-relative `NtCreateFile` opens. Its `NtCreateFile` parameter page,
however, describes `OBJECT_ATTRIBUTES.Attributes` as zero or
`OBJ_CASE_INSENSITIVE`; it does not explicitly list `OBJ_DONT_REPARSE`
there. That mismatch must be resolved for the chosen user-mode API before
freezing exact call arguments.

The `NtCreateFile` page also lists `FILE_DIRECTORY_FILE` compatible
options without `FILE_OPEN_REPARSE_POINT`, while separately documenting
`FILE_OPEN_REPARSE_POINT`. Do not assume that combining those flags is
supported for directory opens. `CreateFileW` documents
`FILE_FLAG_OPEN_REPARSE_POINT` and `FILE_FLAG_BACKUP_SEMANTICS`, but a
final-component-only open does not establish ancestor safety. An
alternative component-by-component open would need retained parent
handles, no-delete share, identity checks, and proof against namespace
remapping between prefix opens and `CreateProcessW` path resolution.

For file bytes, an inspection handle opened with read access and no
`FILE_SHARE_WRITE` or `FILE_SHARE_DELETE` is a candidate to block new
write/delete opens while held. Microsoft documents share-mode
compatibility and notes that an existing writable file mapping can make
such an open fail. This narrows one class of races; it does not by itself
prove that an image section already created from that file matches the
reviewed bytes or that every alternate name/namespace route is excluded.
The selected file system, volume type, ACL, share behavior, and failure
policy need an exact proof. No best-effort fallback open is allowed.

## Required Decision Before Implementation

1. Independently decide whether the debug-event image handle is an
   acceptable identity primitive on the target host and with the existing
   AppContainer/job startup. A null or unqueryable handle denies.
2. Resolve the user-mode no-reparse component-walk API and valid exact
   access/share/create flags. Resolve DOS-device/volume-name substitution,
   retained-handle cleanup, and the runtime's pre-existing opens.
3. Establish a byte-level invariant across reviewed hash, image-section
   creation, event observation, and cleanup. File-ID equality alone is not
   enough. State the attacker and privilege assumptions explicitly.
4. Only after 1-3 are reviewed, authorize a versioned roll of the exact
   launch/plan/receipt flags and corresponding fake-only denial tests.
   A source-only fake adapter may then be qualified separately. Any real
   process attempt needs a fresh exact bounded live authorization.

If any proof obligation remains unresolved, keep the positive native
creator path on HOLD. Denial and fake accounting do not establish
production readiness.

## Primary References

- [Process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)
- [WaitForDebugEvent](https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-waitfordebugevent)
- [CREATE_PROCESS_DEBUG_INFO](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info)
- [OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes)
- [NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile)
- [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)
- [Creating a file mapping object](https://learn.microsoft.com/en-us/windows/win32/memory/creating-a-file-mapping-object)

## Exit State

`EA4E92AX_REVIEW_COMPLETE=YES`

`EXACT_FLAGS_ROLLED=NO`

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`
