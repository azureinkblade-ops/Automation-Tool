# EA-4E.92NK protected-pipe qualification plan

Status: NON-LIVE PLAN / NATIVE PROBE NOT AUTHORIZED / PRODUCTION HOLD.
Parent: `6a9eaad6d5833dcf1489ded837626ccc4694da88`.
Profile: accepted EA-4E.92DE local-container profile only.

## Boundary and correction

92NF-92NJ qualify inert message capture, a post-read observer, a separate
test client PID/creation-time pair, and 92NE parser composition. They do not
qualify the pipe used by a protected issuer. The fixtures use default named
pipe security, which is unacceptable for the issuer. Windows documents that
a default pipe DACL grants broad access, and that generic write includes
`FILE_CREATE_PIPE_INSTANCE`. A protected server must use an explicit
security descriptor and specific client rights.

Strict 92AT exact mapped-byte proof remains REJECT/HOLD and must not be
reported green. It is not silently made a prerequisite of the separately
accepted 92DE local-container profile; that profile instead requires its own
qualified OCI provenance and all remaining issuer/app authority gates.

## Source-only implementation gate

1. Freeze one ceremony-bound pipe name, exact owner/SDDL/mandatory label,
   one-instance and first-instance policy, `PIPE_REJECT_REMOTE_CLIENTS`,
   overlapped message mode, noninheritability, and a 512-byte frame bound.
   The issuer, not the app request, must choose the name and policy.
2. Use native `CreateNamedPipeW` with explicit `SECURITY_ATTRIBUTES`; the
   high-level default constructor is not evidence of the required first-
   instance or remote-client flags. Retain the exact returned handle and
   read back owner, DACL, and label before connecting.
3. In the same-account UAC case, prove that the limited app token cannot
   change the DACL or create a second instance. An ACE granting only narrow
   write to the user SID is insufficient by itself if the same SID owns the
   object. Review the owner and `OWNER RIGHTS` policy before freezing SDDL.
4. Make the app client request only the specific write rights needed for
   one message via `CreateFileW`, not `GENERIC_WRITE`. Keep the 92NG bounded
   read, 92NH same-handle observer, 92NI PID/creation comparison, and 92NE
   canonical parser in one transaction. Any denial discards bytes and never
   falls back to the elevated server token.
5. Test source-only and fake denial paths first. Freeze exact source closure,
   compiler, executable hash, and reviewed command line. No UAC prompt,
   privileged pipe, real app, issuer claim, Docker mutation, receiver,
   model, GPU, or ComfyUI action belongs to this gate.

## Separate one-shot native qualification gate

Only after source review may a new, exact authorization permit one elevated
creator and one limited inert child, one random ceremony pipe, one bounded
message, and exact-handle cleanup. The authorization must pin source commit,
binary SHA-256, operator, executable path/argv, deadline, expected token
pair, and a one-attempt budget. The probe must read back the actual owner,
DACL, label, instance/remote policy, and test the limited client's allowed
specific write plus denied generic write, second instance, `WRITE_DAC`, and
`WRITE_OWNER`. A wrong local account and remote client require a separately
bounded feasible fixture; do not infer their denial from flags alone. Any
unexpected privilege, readback mismatch, orphan, incomplete cancellation,
or cleanup uncertainty is HOLD with no automatic retry.

Passing that inert probe would not issue activation authority or qualify a
real Kilo/OpenCode model call. The trusted app launcher, independent issuer
installation, durable one-shot accounting, OCI receiver provenance, and an
exact separately bounded live ceremony would remain.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
- https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew
- https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-security-identifiers
- https://learn.microsoft.com/en-us/dotnet/api/system.io.pipes.namedpipeserverstream.-ctor
