# EA-4E.92PG Directory2 installer call contract

Status: NON-LIVE DESIGN / NATIVE INSTALLATION HOLD.
Governing parent: `8f45f790aa5d41115708759710d0dc26cf30c174`.
Profile: accepted 92DE trusted local-container host only, not strict 92AT.

## First missing child

The separately pinned elevated installer must obtain ProgramData from
`FOLDERID_ProgramData`, compare it with a trusted manifest root using the
92PC value screen, and retain a handle to the existing ProgramData parent.
It must verify the parent is the expected local filesystem directory, not a
reparse point, and that the exact intended `Hermes` child is absent. Neither
an environment value nor `Test-Path` supplies authority for this decision.

If source review confirms the API contract on this host and volume, the
candidate first-child operation is one `CreateDirectory2W` call for the exact
`Hermes` child. It must request a retained directory handle with no delete
sharing, use `DIRECTORY_FLAGS_DISALLOW_PATH_REDIRECTS`, and supply the exact
reviewed security descriptor in `SECURITY_ATTRIBUTES` at creation. The
descriptor must explicitly protect the DACL and define owner, group,
minimal intended medium read/traverse access, SYSTEM/Administrators control,
and high/no-write-up label. The installer must prove the filesystem supports
persistent ACLs and its token has any privilege required for the intended
owner/SACL before attempting creation. Null/default security attributes or
create-then-rewrite ACLs are not allowed.

`ERROR_ALREADY_EXISTS`, an unexpected object, unsupported API/flag, null or
invalid handle, path redirect, security application/readback mismatch, label
failure, or uncertain result is HOLD. The installer may not adopt, repair,
delete, or rename an unexpected object and may not retry under a new name.
After success, it must screen the returned handle's exact path, file ID,
attributes, owner, protected DACL, label and no-delete-sharing behavior
before attempting the next child. A string-only relookup is insufficient.
All retained ancestor handles stay open through descendant creation and
verification. Each later child follows the same single-create, exact-handle,
descriptor-at-create rule. If a failure leaves a created child behind, record
its exact identity and stop; do not perform broad cleanup in this ceremony.

## Qualification boundary

This call contract is a candidate, not proof that `CreateDirectory2W` makes
the descriptor and label atomic on this volume, that the parent handle
prevents every path substitution, or that the medium token lacks mutation
rights. Those facts require source review, inert failure-path tests, and a
fresh exact bounded native qualification after a pinned installer binary is
available. The native approval must identify source and binary hashes,
operator SID, exact namespace objects, attempt count, deadline, audit and
cleanup policy. No consumed pipe-readback approval applies here.

No installer source was executed, no directory/file/pipe was created, and no
Docker, receiver, model, GPU, ComfyUI or production action occurred. The
installed namespace, full 92NK, issuer, receiver/model and production remain
HOLD.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectory2w
- https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights
- https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath
