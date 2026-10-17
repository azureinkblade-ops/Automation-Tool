# EA-4E.92LK protected pipe access boundary

Status: NON-LIVE DESIGN HOLD / NO PROTECTED PIPE SERVER INSTALLED.
Baseline: `8544a1b89fec6ae4fb4010f9d096ecc084a402df`.

## Same-account UAC boundary

The selected operator path uses the current administrator account with UAC.
The elevated issuer and ordinary app may therefore have the same user SID;
granting that SID narrow write access while giving the same SID full
control through a second ACE is ineffective. The owner of a Windows object
also has implicit `WRITE_DAC` rights by default. A pipe whose owner is the
app's user SID cannot be called protected merely because its DACL grants
that SID only pipe-write rights. The `OWNER RIGHTS` SID is a possible way
to constrain owner-implicit rights, but its exact behavior on this pipe
must be verified with a real limited app token and elevated creator token.

The candidate server must be created by the protected elevated operator
context, with an explicit non-null protected DACL, a reviewed owner and
`OWNER RIGHTS` policy, `FILE_FLAG_FIRST_PIPE_INSTANCE`, one instance,
`PIPE_REJECT_REMOTE_CLIENTS`, non-inheritable handle, bounded message size,
and a ceremony-bound name that app code cannot choose. No default pipe
security descriptor is acceptable. The ordinary app grant may contain
only the specific rights needed to connect and write the challenge; it
must not include `FILE_CREATE_PIPE_INSTANCE`, `WRITE_DAC`, `WRITE_OWNER`,
or generic write. The app client must request those specific rights via
`CreateFileW`; using a high-level generic-write client is not assumed safe.

## Required native qualification

1. From the actual elevated operator token, create one temporary pipe with
   the exact reviewed owner/DACL and creation flags. Read back the owner and
   DACL from the retained pipe handle. Verify the instance and remote-client
   policy through a native probe, not only constants in source.
2. From the actual linked limited token, prove one specific-rights local
   connection and one bounded challenge write, then deny generic-write,
   second-instance creation, `WRITE_DAC`, `WRITE_OWNER`, and any attempt to
   change the pipe DACL. A wrong local account and remote client must deny.
3. Prove the server reads the final message on the impersonating thread,
   binds 92LJ's process and token observations to the independently retained
   app handle, and fails closed on disconnect, timeout, reloader, replay,
   or owner/token drift. There is no issuance or Docker action in this test.

No native positive has yet been performed for the same-account UAC case.
92LF/92LG/92LJ are read-only observations over fixture-created pipes and
do not prove this access boundary. Creating or installing the protected
server, prompting for UAC, launching the app, issuing authority, Docker
mutation, or real Kilo/OpenCode/model execution requires separate bounded
authorization and evidence. Production remains HOLD.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
- https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew
- https://learn.microsoft.com/en-us/windows/win32/secauthz/owner-of-a-new-object
- https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-security-identifiers
