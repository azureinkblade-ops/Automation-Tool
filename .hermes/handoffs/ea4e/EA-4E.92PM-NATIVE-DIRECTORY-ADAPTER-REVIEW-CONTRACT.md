# EA-4E.92PM Native Directory Adapter Review Contract

## Source binding

The pinned Microsoft Win32 metadata SDK header declares `HANDLE WINAPI
CreateDirectory2W(LPCWSTR, DWORD, DWORD, DIRECTORY_FLAGS,
LPSECURITY_ATTRIBUTES)` with five parameters. The public W/A documentation
examples pass six parameters and disagree on the failure sentinel (zero
versus `INVALID_HANDLE_VALUE`). Therefore the header fixes the call shape,
not the observed result behavior on this host.

- Pinned header: https://raw.githubusercontent.com/microsoft/win32metadata/76c04c2021ef4a831a6f1e06d9566002d746139b/generation/WinSDK/RecompiledIdlHeaders/um/fileapi.h
- W documentation: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectory2w
- A documentation: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectory2a

## Proposed fail-closed adapter boundary

1. Bind the Unicode export by exact name with the five-parameter WINAPI
   convention. Do not infer the call shape from the shared example. Keep the
   adapter unreachable from a production command until independently reviewed.
2. Obtain the exact known-folder parent and pinned manifest path from separate
   trusted inputs. Reject a missing, redirected, or noncanonical parent; do
   not treat the 92PI value plan as authentication of either input.
3. Require a volume with persistent ACL support, an elevated issuer with the
   required security privilege, and a non-null security descriptor supplied
   in `SECURITY_ATTRIBUTES` at creation. Pin the descriptor bytes and lifetime
   across the call; never fall back to inherited/default security.
4. Pass the reviewed readback access, read/write-but-no-delete share mask, and
   disallow-path-redirects flag. Make one attempt at the absent first child.
   `ERROR_ALREADY_EXISTS`, redirection, path absence, or uncertainty is HOLD:
   no adoption, repair, retry, or path-based removal.
5. Capture the native last error immediately after the call. Reject both zero
   and `INVALID_HANDLE_VALUE` before constructing an owning handle wrapper.
   A non-sentinel pointer is only a candidate until the exact returned handle
   passes file type, final path, identity, owner/group, protected DACL,
   high/no-write-up label, and effective-rights observation.
6. Keep the returned handle open through observation and dispose that exact
   handle once. Never interpret `CloseHandle` as removal of the new directory.
   If creation may have occurred without an observable handle, stop in HOLD
   and preserve the object for separately governed operator reconciliation.

This is a source-review contract, not an implementation, SDK qualification,
or native test. The local Windows SDK include tree was absent at review time;
the host export-presence check in 92PF does not prove runtime semantics. An
independent ABI/security review and newly pinned source, binary, operator,
objects, deadline, and one-attempt authorization are required before any
mutating native probe. The full 92NK issuer, strict 92AT mapped-byte proof,
real Kilo/OpenCode receiver, and production activation remain HOLD/REJECT.
