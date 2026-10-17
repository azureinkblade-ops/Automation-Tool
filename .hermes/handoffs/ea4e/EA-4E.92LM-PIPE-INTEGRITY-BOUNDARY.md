# EA-4E.92LM pipe mandatory-integrity boundary

Status: NON-LIVE DESIGN HOLD / NO PROTECTED PIPE SERVER INSTALLED.
Baseline: `f7702a5822c9ed775d80d5667351c1aa3590ab81`.

92LK covers discretionary pipe access and same-account owner rights, but it
does not establish the mandatory integrity check. Windows evaluates mandatory
integrity control (MIC) before the DACL. A lower-integrity client may be
denied write access to a higher-integrity pipe even when an explicit DACL ACE
grants the requested write rights. Elevated processes normally run at high
integrity, ordinary processes at medium, and the default mandatory policy is
NO_WRITE_UP. A pipe without a mandatory label is treated as medium; neither
the label nor an unlabeled state may be assumed for a newly created pipe.

The selected same-account UAC path therefore needs both checks to pass:

1. The protected creator must read back the pipe handle's owner, protected
   DACL, and mandatory-label SACL (or confirmed absence) immediately after
   creation. Record the label SID and mandatory policy, not just an SDDL
   string supplied to creation.
2. The app-instance owner must read and retain the actual app token's
   integrity level, enabled/restricted groups, and process identity. The
   current low-integrity Codex token is not a substitute for that token.
3. A bounded native positive must use the actual elevated creator and linked
   limited app tokens to prove one specific-rights connection and challenge
   write. A DACL-only positive or a same-process fixture is insufficient.
4. Negative probes must deny the app generic write, second-instance
   creation, WRITE_DAC, WRITE_OWNER, and security-descriptor changes, plus
   a wrong process/account and a lower-than-app-integrity client. Retain
   92LJ process/token binding and 92LK owner-rights checks.

If the default object label blocks the actual app, a change to the pipe's
mandatory label is a separate, reviewed contract decision. A medium label
could permit the intended medium app to write, but it also changes the
mandatory boundary for other medium callers. The DACL, owner-rights policy,
independent app-process binding, challenge, and replay protection would
still have to deny unauthorized callers. Do not choose a low label or remove
NO_WRITE_UP merely to make a fixture pass. Whether an explicit medium label
can be set and read back on this pipe by the protected creator remains
unproven; fail closed until measured.

The native test must freeze the exact source/binary, elevated and limited
token identities, temporary pipe namespace, one-attempt budget, timeout,
cleanup, and captured security descriptors before execution. It must not
issue authorization, start Docker/Kilo/OpenCode, invoke a model, or activate
production. The separately governed UAC/token-pair probe is NOT authorized
by this design artifact.

Result: 92LK's protected-pipe qualification remains HOLD. The MIC label
and actual app-token compatibility are new explicit gates, not an inferred
pass from existing 92LF/92LG/92LJ fixture tests.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_mandatory_label_ace
- https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
