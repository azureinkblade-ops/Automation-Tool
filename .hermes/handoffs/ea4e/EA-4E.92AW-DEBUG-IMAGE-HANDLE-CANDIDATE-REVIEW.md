# EA-4E.92AW Debug Image-Handle Candidate Review

## Disposition

NON-LIVE SOURCE/API REVIEW on synchronized 92AV commit
`8fa0c0bfc73c896226af9e4a373615619562a953`. This review changes no
production or test source and grants no host-path inspection, native API
call, process creation, fixture execution, thread resume, receiver/model
invocation, GPU/ComfyUI use, or production activation. The 92AU HOLD remains.

`IMAGE_FILE_ID_BINDING_CANDIDATE=DEBUG_CREATE_EVENT_HFILE`

`IMAGE_CONTENT_AND_LIFECYCLE_PROOF=UNRESOLVED`

`TRUSTED_CREATOR_IMPLEMENTATION=HOLD`

`NATIVE_PROBES_AUTHORIZED=NO`

## New Platform Evidence

Microsoft documents that `DEBUG_ONLY_THIS_PROCESS` causes the creating
thread to receive debug events, and `CREATE_SUSPENDED` leaves the primary
thread suspended until `ResumeThread`. On `CREATE_PROCESS_DEBUG_EVENT`,
`WaitForDebugEvent` provides `CREATE_PROCESS_DEBUG_INFO.hFile`, described
as a handle to the process's image file. Unlike
`QueryFullProcessImageNameW`, this is a file handle, not a pathname.
`GetFileInformationByHandleEx(FileIdInfo)` returns a volume serial and
128-bit file ID; Microsoft specifies comparing both to determine whether
two open handles refer to the same file. This is a plausible direct
post-creation file-object comparison against the retained, pre-inspected
runtime handle.

The debug-event image handle may be null, querying `FileIdInfo` may fail,
and the documented handle identity does not by itself prove that the image
section's bytes equal the reviewed SHA-256. All such cases deny. This is a
candidate for independent review, not a positive native receipt.

## Candidate One-Shot Sequence For Review Only

1. Complete five-path, no-reparse inspection and retain every owned handle.
   Hash file bytes through the retained handles. Do not infer ancestor
   safety from `FILE_FLAG_OPEN_REPARSE_POINT` on only the final object.
2. On one dedicated creator thread, consume the attempt before an exact
   `CreateProcessW` call with `CREATE_SUSPENDED`,
   `DEBUG_ONLY_THIS_PROCESS`, and the reviewed AppContainer startup flags.
   The flag combination and interaction with the existing job/attribute
   contract require a separate compatibility review.
3. On that same thread, wait with a finite timeout for exactly the expected
   process-create debug event. Bind event process/thread IDs to the owned
   creation result. Treat any missing, foreign, ambiguous, or extra event
   as unknown; do not resume or retry.
4. Query volume serial and file ID from the event's non-null image `hFile`
   and compare them to the retained runtime handle. A pathname comparison
   is insufficient. Independently review whether the event handle permits
   a post-create byte hash and whether that hash represents the mapped
   image section at creation time.
5. Keep the event, process, thread, image-file handle, and retained path
   handles under one cleanup owner. No `ContinueDebugEvent`, debugger
   detach, `ResumeThread`, or termination sequence is approved here.
   These operations need a separately reviewed fail-closed lifecycle.

This is a design sketch only. Microsoft says `ContinueDebugEvent` enables
the stopped debugged thread to continue and restricts it to the creating
thread. Its interaction with `CREATE_SUSPENDED` and a terminate-without-run
path must be established before any live probe. A timeout or ambiguous
cleanup remains sticky unknown, not permission to try again.

## Remaining Proof Obligations

- Verify on the target Windows build, without weakening the 92AT contract,
  that the debug event's `hFile` is present and supports `FileIdInfo` and
  the required access. Fake injection can test denial but cannot establish
  this OS behavior.
- Prove image-content immutability between the reviewed hash and image
  mapping, including pre-existing writable mappings, alternate streams,
  hard links, replacement, and writable handles. A file-ID match alone is
  not a byte-level proof. Specify the exact share/ACL/handle regime.
- Specify a no-reparse component walk for all five paths. Microsoft's
  `OBJECT_ATTRIBUTES.OBJ_DONT_REPARSE` is a potential mechanism, but exact
  user-mode API, root-directory handling, access/share/open flags, and
  race/cleanup behavior remain unqualified.
- Review debug-flag compatibility with the AppContainer startup attributes,
  job assignment, pre-resume verifier, and one-binding limit. Resolve
  debugger-thread ownership, event-loop timeout, and handle closure.
- Independently review the resulting source/API contract. Only then may
  fake-injected native-adapter source and fail-closed tests be proposed.
  Any real process attempt requires a separate exact bounded authorization.

## References

- [Process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)
- [WaitForDebugEvent](https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-waitfordebugevent)
- [CREATE_PROCESS_DEBUG_INFO](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info)
- [ContinueDebugEvent](https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-continuedebugevent)
- [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)
- [GetFileInformationByHandleEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex)
- [OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes)
- [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [Creating a file mapping object](https://learn.microsoft.com/en-us/windows/win32/memory/creating-a-file-mapping-object)

## Exit State

`EA4E92AW_REVIEW_COMPLETE=YES`

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`NATIVE_INSPECTOR_IMPLEMENTED=NO`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`
