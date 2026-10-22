# EA-4E.92QK Retained-Handle Volume ACL Candidate

The 92QI review left persistent-ACL volume support as a native-issuer
prerequisite. This source-only candidate declares
`GetVolumeInformationByHandleW` against a caller-owned `SafeFileHandle` and
screens the returned `FILE_PERSISTENT_ACLS` flag (`0x00000008`). Failure to
retrieve the information is a denial even if the output flag happens to
contain that bit. Null, invalid, or closed handles are denied before the
native call. The caller retains the handle; this helper does not open,
create, close, or adopt a path. It has no production caller.

Microsoft's documented API retrieves file-system and volume information
associated with the specified file handle. The documented flag means that
the volume preserves and enforces ACLs. It is not a witness of the parent
path, effective client rights, trusted manifest/SID, privilege, or exact
post-create image bytes. The API documentation also notes that SMB does not
support volume-management functions. Reference:
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationbyhandlew

The declaration and pure flag screen passed 7/7 focused inert tests. The
adjacent source-only matrix passed 123/123 before staging. The tests reflect
the ABI, exercise synthetic flags and null-handle denial, and confirm the
reader remains unwired. They never invoke `GetVolumeInformationByHandleW` on
a real handle. Native compatibility, parent binding, effective rights, and
the authenticated issuer remain HOLD. Strict 92AT remains REJECT. No native
owner, Docker mutation, Kilo/OpenCode/model, GPU, ComfyUI, or production
action occurred.
