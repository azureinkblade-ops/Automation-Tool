# EA-4E.92KZ protected path-access contract

Status: NON-LIVE DESIGN CANDIDATE. No protected install or issuer authority.
Baseline: `9c7714495a77c42de0aee6fbf2397ec7a653caa7`.

## Intended witness

The future verifier must observe the approved issuer file, every transitive
dependency, configuration/store file, installation directory, and every
ancestor from the volume root through retained handles. The 92KY topology
match is necessary but not sufficient. Handles must remain open through
security-descriptor observation and byte hashing; path strings alone must
not be reused for the security decision. Recheck the same object identities
immediately before publication and execution. Any failed observation denies.

The operator must bind an expected ordinary app-account SID independently
of the app request. The verifier must obtain that account's real unelevated
impersonation token, including enabled groups and restricted SIDs, from a
reviewed operator boundary. A caller-supplied SID string, simulated token,
or the elevated issuer's own token is not evidence of app-account access.
If the account/token identity or elevation type cannot be established,
deny. An elevated full token must never stand in for the limited app token.

For each retained object handle, obtain owner and DACL with `GetSecurityInfo`.
Reject missing/null DACL and an owner identity not on an independently
approved owner allowlist. With the exact ordinary app impersonation token,
run `AccessCheck` using `MAXIMUM_ALLOWED` and the file-object generic
mapping. Fail closed on API failure, invalid security descriptor, privilege
buffer errors, or ambiguous mapping. Deny if granted rights include any
write-data, append-data, write-EA, write-attributes, DELETE, WRITE_DAC, or
WRITE_OWNER on a file; for a directory also deny add-file,
add-subdirectory, and FILE_DELETE_CHILD. Include inherited and group ACEs.
The complete ancestor chain must pass; protecting only the leaf fails.

Because a security descriptor can change after observation, this is still
not a durable byte witness unless the independently protected installer
and issuer maintain the approved path and object identity across the
installation, publication, and execution boundary. A later path swap,
worktree-sourced dependency, or unchecked loader search path is a denial.
Do not infer that a successful read-only `AccessCheck` alone prevents a
local administrator, whom the revised threat model explicitly trusts, from
mutating the installation.

## Required qualification

- Positive: a separately created protected test tree owned by an approved
  principal, observed using the real unelevated app token. No fake-only
  positive may qualify the Windows boundary.
- Negative: app-owned leaf; writable ancestor; inherited group allow;
  directory add-file, add-subdirectory, or delete-child; leaf write,
  delete, owner, or DACL-change; null DACL; changed token SID/elevation;
  reparse ancestor/leaf; hard-linked target; path replacement between
  observations; missing dependency; changed destination bytes.
- Review native structure layouts, error handling, token-handle lifetime,
  privilege-set buffer sizing, and the object-specific generic mapping.
- Bind an exact reviewed binary/dependency SHA-256 closure and an exact
  independent operator approval before any protected installation.
- Run focused, adjacent, staged-tree, and committed-tree tests. Record
  permission-dependent skips as gaps, never as passes.

No existing 92KY result proves any of these ACL conditions. A live install
or UAC prompt needs separately bounded authorization; Docker mutation and
real Kilo/OpenCode/model calls require distinct action-specific authority.
Production HOLD.

## API basis

- https://learn.microsoft.com/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck
- https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_elevation_type
