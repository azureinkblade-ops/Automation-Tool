# EA-4E.92OT creator read-rights correction

Status: NON-LIVE SOURCE CONTRACT / NATIVE FILE OPEN HOLD.
Governing parent: `e2c0a14b31720753c539f5fa6d8eed651d12cfb7`.

The 92OM elevated creator mask included `FILE_WRITE_DATA`, `READ_CONTROL`,
and `ACCESS_SYSTEM_SECURITY`, but not `FILE_READ_DATA` or
`FILE_READ_ATTRIBUTES`. The 92OQ creator-side exact-byte hash and 92OS
retained-handle `FileIdInfo` observation cannot be assumed to work through
that insufficient handle. The source-only creator mask now includes those
two specific read rights:

```text
creator desired access = FILE_READ_DATA | FILE_WRITE_DATA |
                         FILE_READ_ATTRIBUTES | READ_CONTROL |
                         ACCESS_SYSTEM_SECURITY = 0x01020083
creator share mode     = FILE_SHARE_READ = 0x1
reader desired access  = FILE_READ_DATA | FILE_READ_ATTRIBUTES |
                         READ_CONTROL = 0x00020081
reader share mode      = FILE_SHARE_READ | FILE_SHARE_WRITE = 0x3
```

The old `0x01020002` mask is explicitly denied by the inert screen. The
read grants apply only to the trusted elevated creator, not the medium app.
They do not prove that `FileIdInfo` succeeds with these rights on the target
filesystem, that the file bytes match after flush, or that the installed
ACL/label is correct. Native handle behavior must be qualified under a new
exact authorization. No path was opened and no receiver/model, Docker,
GPU, ComfyUI, or production action occurred.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
- https://learn.microsoft.com/en-us/windows/win32/fileio/file-access-rights-constants
- https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex
