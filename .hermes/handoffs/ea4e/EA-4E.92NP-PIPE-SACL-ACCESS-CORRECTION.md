# EA-4E.92NP pipe SACL access correction

Status: NON-LIVE SOURCE CORRECTION / OPEN NOT INVOKED / PRODUCTION HOLD.
Parent: `78d699ea789786b1104bea9f048c20e00cba3146`.

Source review found that a retained pipe handle intended for SACL readback
must request `ACCESS_SYSTEM_SECURITY` at creation, and the creator must
have `SeSecurityPrivilege` enabled. The 92NO source did not request that
access. `Ea4eProtectedPipeCreatorCandidate.Open` now explicitly includes
the access bit; it does not enable a privilege or silently retry without
the bit. The issuer-owned pipe name now contains both the approved ceremony
UUID and a fresh random UUID. A failed native create captures the Win32
error before disposing the invalid handle.

The source-only fixture invokes only `BuildSddl`, `ProposedOpenMode`, and
`BuildPipeName`. It never invokes `Open`, creates a pipe, or prompts for UAC.
The expanded template and descriptor matrix has 39 cases. The native
qualifier must still prove actual privilege handling, owner/DACL/SACL
readback, specific-rights app write, generic-write denial, second-instance
denial, remote denial, cleanup, and binding to the real app instance. The
Windows pipe API describes `PIPE_ACCESS_INBOUND` clients as using
`GENERIC_WRITE`; whether the proposed narrower `FILE_WRITE_DATA` grant
permits the intended connection is unresolved and must be measured in the
bounded native test. No policy may be weakened automatically to make it
connect.

No issuer issuance, Docker mutation, Kilo/OpenCode/model invocation,
GPU/ComfyUI activity, or production activation is authorized here.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew
- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/en-us/windows/desktop/SecAuthZ/sacl-access-right
