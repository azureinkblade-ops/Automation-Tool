# EA-4E.92NT protected-pipe readback source candidate

Status: NON-LIVE SOURCE AND SYNTHETIC DESCRIPTOR QUALIFICATION / NATIVE HOLD.
Parent: `f303f26bf051bbf977083a840d296ec2bbd90805`.

`Ea4eProtectedPipeReadbackCandidate.Read` is an uninvoked native candidate.
It uses the retained `SafePipeHandle` with `GetSecurityInfo(SE_KERNEL_OBJECT)`
to request owner, group, DACL, and SACL, bounds and copies the returned
descriptor, then frees the native buffer. A missing access right, disabled
`SeSecurityPrivilege`, invalid descriptor, or mismatched structure denies.
The method does not create a pipe or enable a privilege.

The pure byte screen requires Administrators owner and group, exactly three
allow ACEs for the individual app SID, SYSTEM, and Administrators, exact
`FILE_WRITE_DATA` for the app, and the existing protected-DACL/medium-label
screen. It does not prove effective token access or the created object's
flags. A synthetic round-trip exposed that calling .NET Framework's SDDL
formatter on the parsed descriptor emitted an empty `S:` field. The screen
therefore consumes the parsed `RawSecurityDescriptor` directly rather than
using a lossy string round-trip.

Focused synthetic matrix: 12 passed, 0 failed. Combined with the existing
descriptor and creator-template tests: 51 passed, 0 failed. No test calls
native `Read` or `Ea4eProtectedPipeCreatorCandidate.Open`.

The separately bounded 92NK native gate remains required: enabled token
privilege, actual owner/DACL/SACL readback, limited client specific-rights
write, denied generic write/second instance/WRITE_DAC/WRITE_OWNER, timeout,
and exact-handle cleanup. This source checkpoint is not a protected issuer,
Docker authorization, agent handoff, or production activation.

API basis:
- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
- https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getsecuritydescriptorlength
