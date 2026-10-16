# EA-4E.92LA protected path-access candidate

Status: NON-LIVE / READ-ONLY ACL SNAPSHOT CANDIDATE. Not an issuer witness.
Baseline: `bd8cff3d5937c1b7df4e69338e0a1fe17b946691`.

The 92KY topology observer now permits an in-process callback while all
root, ancestor, and leaf handles remain open. The new candidate binds an
expected SID to the current process's unelevated token, duplicates it to an
impersonation token, retrieves owner/group/DACL from each retained handle,
rejects an app-owned object or null DACL, and uses `AccessCheck` with
`MAXIMUM_ALLOWED` to deny file or directory mutation rights. It returns a
snapshot result only; no write, execution, elevation, or Docker operation.

During focused testing, an app-owned file initially returned a generic
access denial because `ConvertSidToStringSid` resolved its ANSI entry point
while the returned pointer was read as Unicode. The P/Invoke now pins the
Unicode entry point. A privilege-buffer retry also now clears the freed
pointer before reallocation. Focused tests: 4 passed / 0 failed. Adjacent
fake-only tests: 599 passed / 3 skipped / 0 failed. The three skips are
existing Windows hard-link/symlink creation permission limits in the 92KY
suite, not passes. A read-only probe of two Windows system binaries denied
at the 92KY multi-link guard and is not a protected-path positive test.

The candidate intentionally has no independent app-token source: its probe
uses the current process token and receives expected SID from the caller.
That cannot supply the 92KZ operator witness. It also lacks an approved
owner allowlist, a protected test tree with a positive ACL result, byte and
dependency pinning on the retained handles, a reviewed protected binary
closure, protected installation, and a durable object-identity check through
later execution. The checks can deny a mutable path but cannot authorize
an issuer, network/container mutation, or a real receiver/model call.

No protected install/UAC prompt, Docker mutation, Kilo/OpenCode/model call,
GPU/ComfyUI, or production activation occurred. Production HOLD.

API basis:
- https://learn.microsoft.com/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck
- https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights
