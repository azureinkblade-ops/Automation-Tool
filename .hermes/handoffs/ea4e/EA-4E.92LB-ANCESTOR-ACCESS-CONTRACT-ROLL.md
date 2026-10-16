# EA-4E.92LB ancestor-access contract roll

Status: NON-LIVE / READ-ONLY ACL SNAPSHOT CORRECTION. Production HOLD.
Baseline: `2a4c7be0bf8c2d97e2b98b62a7161d6eaccc263a`.

The 92KZ wording required denying all creation rights on every ancestor.
This was too broad for the local Windows volume root: `C:\` grants ordinary
authenticated users add-subdirectory but not ownership, DACL changes,
delete-child, or the ability to replace the protected `Program Files` child.
Under the original 92LA mask, that unrelated-sibling creation right denied
every path below this volume, even when the protected subtree was immutable.

The candidate now requires a named protected installation root. It checks
the root and everything beneath it for all write/create/delete/owner/DACL
rights. Above that root, it denies rights that can alter the ancestor or
replace its protected child, but does not treat add-subdirectory alone as
substitution. Add-file remains denied on an ancestor: the documented
`FSCTL_SET_REPARSE_POINT` access check accepts `FILE_WRITE_DATA` or
`FILE_WRITE_ATTRIBUTES`, and `FILE_WRITE_DATA` is the directory add-file
bit. This is a narrow forward roll of 92KZ, not retroactive evidence that
the 92KZ contract passed. The protected root itself is supplied by the
test caller; a production verifier must bind it independently.

Focused topology/ACL tests: 17 passed, 3 Windows permission skips. The
adjacent fake-only suite: 605 passed, 3 skips, zero failures. A read-only
probe outside the Codex filesystem sandbox, under the standard unelevated
Windows token, returned `MATCH:ACL_SNAPSHOT_ONLY` for the existing
`C:\Program Files\Git\etc\gitconfig` with protected root
`C:\Program Files\Git`. The same probe returned `DENY:APP_OWNS_OBJECT`
for the mutable source file in this worktree. Inside the lower-integrity
Codex sandbox, the protected-file probe denied access; that denial is not
counted as a positive result. These are diagnostics against existing files,
not a dedicated protected issuer installation or a durable byte witness.

Still absent: independent app-token and protected-root binding, approved
owner allowlist, positive test in a separately provisioned issuer fixture,
reviewed binary/dependency closure, byte hashing on held handles, durable
post-install identity, and a protected installer/issuer. No UAC prompt,
file permission change, protected installation, Docker mutation, real
receiver/model call, GPU/ComfyUI, or production activation occurred.

API basis:
- https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights
- https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fsa/4aeefef8-92c3-4abc-af7a-a610caf8a165
