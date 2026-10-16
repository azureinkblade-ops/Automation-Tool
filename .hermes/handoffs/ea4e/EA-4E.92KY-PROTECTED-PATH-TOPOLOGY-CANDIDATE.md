# EA-4E.92KY protected path-topology candidate

Status: NON-LIVE / READ-ONLY TOPOLOGY CANDIDATE. Not an ACL, install, or issuer qualification.
Baseline: `4f826ee0d824e92d7db6be485492ecd4e6ae4511`.

`Ea4eProtectedPathTopologyCandidate.Denial` accepts only a canonical local
drive path. It opens the root, each ancestor, and a single-link target file
by handle with `FILE_FLAG_OPEN_REPARSE_POINT`; it checks file attributes,
reparse tags, object types, link count, and final paths while retaining the
handles through the observation. It never opens a file for write or runs it.

Focused Windows tests: 8 passed, 2 skipped outside the filesystem sandbox.
The hard-link denial was exercised. Symlink-file and symlink-ancestor tests
were skipped because this token lacks symlink-creation privilege (WinError
1314), not counted as passes. A normal file only earns `MATCH:TOPOLOGY_ONLY`.
The filesystem-sandbox run passed 7 tests and skipped 3, including hard-link
creation (WinError 5). The adjacent fake-only regression run passed 595 tests
and skipped the same 3 permission-dependent cases; it had zero failures.

This is an observation at one time, not a protected-path attestation. It
does not inspect owner or DACL, determine the app token's effective write
rights, hold handles for subsequent byte use, qualify dependencies, or
prevent a later path swap. A production path must combine handle-stable
topology, owner/effective-access and reparse checks on every ancestor,
exact byte/dependency pinning, and a separately reviewed installation.

Microsoft API references:
- https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-createfilew
- https://learn.microsoft.com/en-us/windows/desktop/api/winbase/nf-winbase-getfileinformationbyhandleex
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/ns-fileapi-by_handle_file_information

No UAC, protected installation, Docker mutation, receiver/model call,
GPU/ComfyUI, or production activation occurred. Production HOLD.
