# EA-4E.92PF CreateDirectory2W export preflight

Status: READ-ONLY API AVAILABILITY / INSTALLATION HOLD.
Governing parent: `3a43d0572137263003c4d61554c790fcad2b5098`.
Profile: accepted 92DE trusted local-container host only.

The host reports Windows build 26200. A source-only C# probe called
`GetModuleHandleW` and `GetProcAddress` and found the `CreateDirectory2W`
export in kernel32. It did not import or call that creation function. Focused
export tests passed 2/2. No directory, file, pipe or token was modified.

Microsoft documents `CreateDirectory2W` on Windows 11 24H2 and later. Its
creation call can supply a security descriptor and return a directory handle,
and it defines `DIRECTORY_FLAGS_DISALLOW_PATH_REDIRECTS`. These documented
properties make it a candidate for the 92PE first-child creation race, not
a qualified solution. The security descriptor must be pinned and applied at
creation, not in a later create-then-secure step. The returned handle must be
retained without delete sharing, screened for exact object identity,
reparse absence, owner/protected DACL/high label, and used to constrain
creation of each descendant. A pre-existing name, wrong filesystem security
capability, unsupported flag, failed descriptor readback or uncertain result
is HOLD; do not adopt or delete an unexpected object.

The source has no installer, path creation, receiver or model route. Export
presence and a supported OS build do not establish creation semantics on this
volume, effective medium-token rights, a trusted manifest, or a durable
issuer. Any native installation/probe requires a separately reviewed exact
source/binary/operator/object/deadline/one-attempt authorization. Existing
readback approvals are consumed. Full 92NK and production remain HOLD.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectory2w
- https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights
