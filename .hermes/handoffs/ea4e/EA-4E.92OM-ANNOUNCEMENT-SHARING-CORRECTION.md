# EA-4E.92OM announcement sharing correction

Status: NON-LIVE SOURCE-ONLY / NO FILE OPEN OR INSTALLATION.
Governing parent: `565a6f11796e919df9a82501a726e3f6f30a06b9`.

92OL proposed retaining the elevated creator's write handle while a medium
coordinator opens the same record for reading. Windows sharing checks are
bidirectional: a reader opened with only `FILE_SHARE_READ` conflicts with an
already open writer. Therefore the previous phrasing must not be implemented
as a reader share mask of read-only. The exact candidate masks are:

```text
creator desired access = FILE_WRITE_DATA | READ_CONTROL | ACCESS_SYSTEM_SECURITY
                      = 0x01020002
creator share mode     = FILE_SHARE_READ                 = 0x00000001
reader desired access = FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL
                      = 0x00020081
reader share mode     = FILE_SHARE_READ | FILE_SHARE_WRITE
                      = 0x00000003
```

The creator must hold enabled `SeSecurityPrivilege` for the system-security
right and must fail closed if it cannot read back the label/SACL. Neither
handle shares DELETE. The creator's retained handle does not share
WRITE with subsequent opens. The reader's WRITE-sharing flag is necessary to
coexist with the already open creator writer; it is **not** a grant of write
access to the reader. Directory/file DACL, owner-rights behavior, high label,
and limited-token effective access still need native proof. If any of those
observations fail, a compatible share mask cannot rescue the ceremony.

The existing `Ea4eProtectedPathTopologyCandidate.DenialWithReadableLeaf`
uses a read-only share mode for its leaf and is not suitable for this retained
writer design without a reviewed change. No such change is made here.

`Ea4eAnnouncementSharePolicyCandidate` freezes only these four integer masks.
Its CLI fixture exposes `masks` and `screen`, not native `CreateFileW`; the
12-case focused matrix passed. Next, implement and source-review a retained
record observer with this compatible sharing, exact root/handle checks,
bounded EOF-confirmed read, and separately qualified security readback.
No file, pipe, Docker, receiver, model, GPU, ComfyUI, or production action
occurred. Full 92NK and production remain HOLD.

API basis: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
