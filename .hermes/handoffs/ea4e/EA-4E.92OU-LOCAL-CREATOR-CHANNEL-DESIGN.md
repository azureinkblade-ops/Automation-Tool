# EA-4E.92OU local creator channel design

Status: NON-LIVE DESIGN / CHANNEL IMPLEMENTATION AND NATIVE QUALIFICATION HOLD.
Governing parent: `9391425eb929af6dc6e503b88ce8af8e06d0fbb6`.
Profile: accepted 92DE trusted local-container host only; strict 92AT is unchanged.

## Proposed channel

The trusted medium coordinator creates one random, ceremony-specific local
named-pipe server before launching the pinned elevated creator. This channel
is distinct from the protected issuer pipe. It is used only to deliver the
fresh coordinator nonce and return a creator attestation. Its name is never
accepted from a request or an environment variable. The server uses
`FILE_FLAG_FIRST_PIPE_INSTANCE`, one instance, `PIPE_REJECT_REMOTE_CLIENTS`,
an explicit DACL restricted to the intended account, Administrators and
SYSTEM, and a bounded connection/read/write deadline. Actual creation masks
and descriptor readback must be reviewed separately. A failure to create the
first instance is HOLD, not a retry with another name.

The coordinator launches an exact, separately pinned elevated creator with
the Windows `runas` verb and requests `SEE_MASK_NOCLOSEPROCESS`. It retains
the returned process handle and records PID, creation time, image identity,
token user, elevation, and deadline. If no process handle is returned, UAC
is denied, or any observation is uncertain, the ceremony stops. A parent-
child claim in a command line is not process authentication. In particular,
this design does not assume that `ShellExecuteEx` inherits anonymous pipe
handles; the documented explicit handle-list mechanism belongs to
`CreateProcess` and is not silently transferred to the UAC path.

After one client connection, the server obtains the connected client's PID
from that same pipe instance and matches it to the retained creator process
handle, including creation time and still-running state. The client must be
the pinned elevated process; a PID alone is insufficient because of reuse.
The medium coordinator sends the fresh nonce and ceremony ID only after this
match. The creator then returns one bounded, canonical attestation that binds
the same nonce and ceremony, creator identity, installer manifest identity,
protected-pipe readback result, retained announcement-record volume/file ID,
record SHA-256, and creator-observed descriptor digest including the label.
The coordinator verifies the response against its independent launch,
installer, and retained-file observations before any issuer-pipe connection.

No JSON field or digest is independently authenticated merely because it is
well-formed. For the accepted 92DE profile, the trust root is the verified
local app account/process plus the pinned elevated executable and the
same-instance connected-process check. If the launch handle cannot be tied
to the connected client, the channel is unauthenticated and HOLD. The
elevated creator should independently verify the server identity or use a
separately reviewed handshake; one-sided PID verification is insufficient
against an untrusted server. The exact two-way handshake and its Windows
API behavior remain open.

The transcript must be single-use: one connection, one nonce exchange, one
attestation, bounded lengths, explicit framing and EOF, no reconnect, no
fallback channel, and durable ledger consumption before issuer-pipe use.
Expired deadlines, mismatched identities, extra frames, partial I/O,
unexpected process exit, unverified cleanup, or an uncertain ledger outcome
are HOLD with no automatic retry. Audit must distinguish UAC denial, launch
failure, pipe creation/connection denial, identity mismatch, malformed
transcript, and cleanup uncertainty without logging secrets.

## Qualification order

1. Freeze exact server/client masks, DACL, integrity label, message framing,
   process/token observations, and the two-way handshake in source.
2. Fake-test denial paths and a source-only Windows API fixture. No native
   launch or pipe connection is permitted by this design checkpoint.
3. Independently verify installer manifest and creator record descriptor
   observations, then request a fresh exact one-shot authorization for an
   inert native channel probe. Do not reuse prior native readback approvals.
4. Only after the native channel, durable ledger, and limited-client gates
   pass may a separate real receiver/model qualification be proposed.

This is a candidate, not a qualified secure channel. It does not install a
namespace, launch a process, open a pipe, issue authorization, activate
production, or run Kilo, OpenCode, models, GPU, or ComfyUI. Full 92NK and
production remain HOLD.

Primary Windows references:

- https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea
- https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid
- https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-shellexecuteinfoa
- https://learn.microsoft.com/en-us/windows/win32/procthread/creating-processes
