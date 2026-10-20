# EA-4E.92OL installed announcement namespace design

Status: NON-LIVE CANDIDATE DESIGN / INSTALLATION AND NATIVE OBSERVATION HOLD.
Governing parent: `0ac6ed92aa3d62be31044b84d7aafed339948850`.
Profile: accepted 92DE local-container trust model only, not strict 92AT.

## Candidate boundary

An administrator-installed directory under the machine-wide ProgramData
known-folder path is the candidate announcement namespace. The suffix is
`Hermes\EA4E\IssuerAnnouncements\v1`. Its location must come from a trusted
installation manifest and `FOLDERID_ProgramData`, never from a request,
environment variable, current directory, or per-user temp path. Installation
must predate a ceremony and be audited separately. No path or ACL has been
installed by this checkpoint.

The installer would own the directory with a protected DACL: SYSTEM and
enabled Administrators may administer it; the exact intended medium app SID
may list/traverse/read but not create, append, write, rename, delete, change
security, or take ownership. The owner should not be the same user SID that
the filtered medium token carries. The directory and each record need an
explicit high-integrity, no-write-up label and handle-based descriptor
readback. Inheritance and effective rights must be tested under the actual
limited token, not inferred from an SDDL string. Same-user UAC split-token
and owner-rights behavior require native qualification before acceptance.

The elevated creator, after its protected pipe handle passes structural
readback, would create exactly one ceremony-named record with create-new
semantics, explicit descriptor, a no-delete/no-write-sharing policy, and a
retained file handle. It writes one 92OJ canonical record, flushes it, and
keeps the handle until the ceremony ends. An existing name, short write,
failed flush, security mismatch, reparse point, or inability to retain the
handle is HOLD with no alternate path. The random pipe name is never supplied
by the medium client. The creator must have a separately qualified way to
receive the coordinator's fresh nonce; that channel is still unresolved.

The medium coordinator opens the installed directory and exact record with
open-existing and open-reparse-point semantics, retains the handles, and
denies any reparse tag. It obtains owner/DACL/label and file identity from
the opened objects, reads at most 1024 bytes from that same file handle,
requires EOF rather than accepting a valid prefix with trailing bytes, and
passes those bytes to 92OJ against independently pinned expected values.
The coordinator must compare the creator PID and creation time with its
retained launch handle and re-observe that process after reading. A path
relookup or record copy is not authority. A file ID and volume serial can
help detect handle substitution, but do not replace ACL/creator checks.

The separate durable ceremony ledger must consume the nonce and record
identity at most once before any client connection. A process-local 92OK
lease is insufficient after restart. Crash, stale record, expired deadline,
replay, unexpected file replacement, or uncertain ledger outcome is HOLD;
there is no automatic retry and no cleanup by broad path deletion. Cleanup
may only close retained handles and remove exact objects under a separately
qualified installer/creator policy. An orphan is investigated, not silently
treated as a new ceremony.

## Qualification order

1. Review the installer manifest, exact path, owner, DACL, label, and trusted
   launch/nonce channel in source. Keep a default-deny path.
2. Implement a source-only retained-handle observer and denial tests for
   reparse, ACL drift, file-ID drift, short read, process drift, stale/replay,
   crash, and uncertain cleanup. Do not connect a pipe.
3. Only after source closure and pinned binary hashes, request a new bounded
   authorization for one inert native install/readback probe. That probe
   cannot issue activation authority or launch Kilo/OpenCode.
4. A later separately authorized limited-client pipe probe must still prove
   effective rights and same-handle identity. Production remains HOLD.

This design does not certify the filesystem, installer, token boundary,
creator-to-coordinator nonce delivery, or durable one-use ledger. It changes
no runtime defaults. No native file/pipe, Docker, receiver, model, GPU,
ComfyUI, or production action occurred.

Primary Windows API references:

- https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info
- https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control
