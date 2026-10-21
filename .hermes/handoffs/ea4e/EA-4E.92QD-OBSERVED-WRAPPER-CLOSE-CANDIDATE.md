# EA-4E.92QD Observed Wrapper Close Candidate

This source-only candidate addresses the 92QC independent review's medium
wrapper-close finding. A dedicated directory `SafeHandle` transfers the
non-sentinel result from the raw pre-wrapper edge and records the result of
its one `ReleaseHandle` call. The owner checks that result after disposal on
denied readback or exception paths. Failed or not-yet-observed release is
reported as `DENY:WRAPPER_CLOSE_UNCERTAIN`; it is not converted to a
successful cleanup claim, retried, adopted by path, or manually closed through
`DangerousGetHandle`. A successful readback still returns the one retained
owner to the caller; no production caller is wired.

The file identity, directory shape, and descriptor readback helpers now
accept `SafeHandle` so both existing `SafeFileHandle` callers and this
directory owner use the same P/Invoke observation path. The owner retains
the distinct pre-wrapper raw-close status and copies the native creation
last error. A separate output carries an observed wrapper release error;
zero is not interpreted as a successful release. No native release outcome
has been observed in this checkpoint.

Focused inert owner/shape/descriptor tests passed 29/29. The adjacent
non-live matrix, including the existing file identity and file descriptor
paths, passed 110/110. The tests compile the candidate sources but only
exercise pre-call, pure classifications, and invalid handles. They do not
create a directory, exercise `ReleaseHandle` on a valid native handle, or
establish the P/Invoke and effective-rights behavior at runtime.

Source owner **HOLD pending new independent review**; native issuer **HOLD**;
receiver/model/production **HOLD**. The 92QC one-review authorization was
consumed on the predecessor and does not cover this source. The independently
identified high finding also remains: parent/manifest/SID provenance,
ACL-capable volume, privilege, first-child absence, and limited-client
effective rights are unproved. Strict 92AT mapped-byte proof remains REJECT.
No native create, Docker mutation, Kilo/OpenCode/model call, GPU, ComfyUI, or
production activation occurred.

Design basis: Microsoft documents that `SafeHandle.ReleaseHandle` is called
once and returns whether cleanup succeeded; a false return can mean a leak.
This source candidate does not infer closure from `Dispose` alone.

- https://learn.microsoft.com/en-us/dotnet/api/system.runtime.interopservices.safehandle.releasehandle?view=netframework-4.8.1
- https://learn.microsoft.com/en-us/dotnet/framework/debug-trace-profile/releasehandlefailed-mda
