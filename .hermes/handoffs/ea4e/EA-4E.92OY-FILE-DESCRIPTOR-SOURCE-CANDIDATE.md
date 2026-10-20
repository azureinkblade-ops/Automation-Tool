# EA-4E.92OY retained file descriptor source candidate

Status: NON-LIVE SOURCE CHECK / NATIVE FILE READBACK HOLD.
Governing parent: `7a91fff209c9d8eeac6a6e847e0aa34dafbc9990`.

The source-only `Ea4eAnnouncementFileDescriptorCandidate` requests
owner/group/DACL/SACL/label from a caller-owned retained file handle with
`SE_FILE_OBJECT` and information mask `0x1f`. It screens a bounded binary
security descriptor for Administrators owner/group, a protected exact
three-ACE DACL, an app read-only ACE (`0x00020081`), trusted SYSTEM and
Administrators file-all ACEs (`0x001f01ff`), and one high-integrity
no-write-up label. Unknown ACEs, broad trustees, app write, missing label,
unprotected DACL, malformed or trailing descriptor bytes all deny.

The inert fixture compiles the candidate and tests static SDDL/binary
screens only. It has no native `Read` CLI. An initial malformed-SDDL test
found an uncaught `SystemException`; that denial path was fixed before
staging. The final focused matrix passed 16/16. These tests do not show
that the intended ACL can be installed, that `GetSecurityInfo` succeeds
under a scoped privilege on the target handle, or that the medium token has
the intended effective rights. The binary descriptor digest must be bound
to an authenticated creator attestation and installer manifest, not merely
copied into a record.

No native file/pipe, UAC process, receiver, model, Docker, GPU, ComfyUI, or
production action occurred. Full 92NK, issuer, and production remain HOLD.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control
