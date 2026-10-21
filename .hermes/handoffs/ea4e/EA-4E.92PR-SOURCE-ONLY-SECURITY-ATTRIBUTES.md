# EA-4E.92PR Source-Only Security Attributes

Status: INERT MARSHALLING PASS / NATIVE CREATE HOLD. Parent:
`511b8c8af071e150957f257ba13156370d3e4df8`.

The new `Ea4eDirectory2SecurityAttributesCandidate` first screens the exact
directory SDDL, converts it to a self-relative descriptor byte array, and
copies those bytes to unmanaged memory. It supplies an injected observer with
a non-null pointer to a sequential `SECURITY_ATTRIBUTES` structure whose
length is the marshalled structure size, descriptor pointer references the
allocated bytes, and inherit-handle flag is zero. Both allocations remain
live through the observer call and are freed afterward. An absent observer
or invalid descriptor denies before allocation. This candidate has no
`DllImport` or native creation call site.

Microsoft's `SECURITY_ATTRIBUTES` definition has a DWORD length, descriptor
pointer, and BOOL inherit flag. The `CreateDirectory2W` page specifies a
descriptor supplied at creation and the disallow-path-redirects flag:

- https://learn.microsoft.com/en-us/windows/win32/api/wtypesbase/ns-wtypesbase-security_attributes
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectory2w

An inert compiled observer compared the descriptor bytes, structure length,
non-null pointer, and zero inherit flag. Its first test run failed only at a
fixture delegate-inference compile error; an explicit delegate construction
fixed that without changing candidate behavior. Focused source matrix 28/28;
adjacent 92P matrix 61/61; all 50 `Ea4e*.cs` candidate sources compiled as
an ignored diagnostic library. Staged-byte and committed-tree verification
are recorded in the paired Obsidian continuation note.

This is not a native ABI/runtime qualification. The existing five-argument
`CreateDirectory2W` declaration is still uncalled; the documented W/A
failure-sentinel discrepancy remains. No directory was created or inspected.
The first-child returned-handle validation, trusted parent and manifest
inputs, persistent-ACL volume, elevated privilege, independent source/security
review, and exact one-shot native authorization remain prerequisites. The
issuer, Kilo/OpenCode receiver/model, and production activation remain HOLD.
