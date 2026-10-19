# EA-4E.92NA kernel pipe-client process lease candidate

Status: NON-LIVE READ-ONLY CANDIDATE / NOT APP AUTHORITY / PRODUCTION HOLD.
Parent: `857e0fa2b0073da0732dd5da1ecdcaea45b56ecf`.
Profile: accepted 92DE local-container profile only. Strict 92AT remains
REJECT/HOLD on exact mapped-image-byte proof.

The new native candidate reads the connected named-pipe client PID from the
pipe handle, opens a process handle with only query-limited-information and
synchronize rights, checks liveness and creation time, and keeps that handle
open during one read-only callback. It rechecks the pipe PID and process
liveness before returning a match. The 92MZ path observation can now use this
kernel-derived handle instead of a fixture-supplied expected process handle.
No process is launched or terminated, and a callback match has no grant or
issuance semantics.

Windows API basis: [GetNamedPipeClientProcessId](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid)
reports the connected pipe client PID;
[OpenProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess)
opens a handle subject to process security;
[GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes)
requires process query rights and returns creation time; and
[WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject)
requires synchronize rights for a process handle. These APIs do not attest
app package bytes, prove which process wrote each pipe message, or establish
an independently approved operator policy.

Changed files:

- `tools/Ea4ePipeClientProcessLeaseCandidate.cs`
- `tools/Ea4ePipeClientPathObservationCandidate.cs`
- `tests/hermes_core/fixtures/ea4e92na_pipe_process_lease_probe.cs`
- `tests/hermes_core/test_ea4e92na_pipe_process_lease.py`
- `tests/hermes_core/fixtures/ea4e92mz_pipe_client_path_probe.cs`
- `tests/hermes_core/test_ea4e92mz_pipe_client_path_observation.py`
- this evidence file

The new fixture proves a self-client handle is live with a nonzero creation
time, and that callback denial, missing observer, and missing pipe deny.
The composed path fixture proves the kernel-derived branch reaches a writable
file's owner/effective-rights denial and rejects a wrong client SID. Its
self-process pipe client is inert and not a qualified app-instance receipt.

Current-tree adjacent gate: 139 passed, 3 permission-based skips, 0 failed
across 92NA, 92MZ, 92KY, 92LC, 92LD, 92LA, 92LF, 92LG, 92LJ, 92LN, 92MO,
92MP, 92MR, 92MS, 92MV, and 92MW. Native pipe tests ran in the permitted
environment because this host's filesystem sandbox blocks local fixture
pipe connections before the tested observations.
Exact staged tree `9fcdd9bced5f9f9abc1eb56531697d4f836d63dc` repeated
the same gate: 139 passed, 3 skipped, 0 failed. This evidence-text update
does not change source or tests.

This candidate is not an app-instance launcher or identity witness. The
pipe/server ownership, local-only security descriptor and integrity label,
canonical app package and process identity, request/ceremony nonce, approved
policy and binary, store/authority observations, and protected installation
remain open. It must not issue a v5 grant or authorize Docker, a Kilo/OpenCode
receiver/model call, GPU/ComfyUI, or production activation.
