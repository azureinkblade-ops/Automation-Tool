# EA-4E.92OJ inert announcement-record contract

Status: NON-LIVE SOURCE-ONLY / NO INSTALLED NAMESPACE OR NATIVE CLIENT.
Governing parent: `4342875bc36017cb508c8d4c90290e5b3333172f`.

The pure `tools/ea4e92oj_pipe_announcement.py` decoder accepts only a
canonical UTF-8 JSON object of at most 1024 bytes with an exact v1 field set.
It binds a nonzero ceremony ID, distinct coordinator nonce, pipe name whose
ceremony component matches, pinned creator executable SHA-256, PID, process
creation time, issuance time, and exact deadline. The coordinator must supply
these expected values independently of the record. It denies duplicate or
unknown fields, alternate encodings, noncanonical types, mismatches, future
issuance, expiry, and a lease longer than two minutes.

This is byte validation only. The candidate does not read a file, inspect a
Windows token or security descriptor, create/connect to a pipe, or own a
one-use ledger. A replay with the *same* expected nonce and still-valid
deadline is not prevented by this parser. It must be denied by a separate
retained ceremony state machine. No authority can be inferred from a matching
JSON record until the installer, parent directory, file handle, owner/DACL,
reparse policy, object identity, creator process, and one-use accounting are
independently qualified. The preinstalled path and ACL are not frozen here.

The next non-live gate is a source-only retained-handle observer and one-use
state machine. It must reject substitution between path lookup and read,
stale/replayed records, creator crash, and uncertain cleanup. A native
installation or limited-client probe still requires a separate exact bounded
authorization. Strict 92AT mapped-byte proof remains REJECT/HOLD independently
of the accepted 92DE local-container profile. Production, Docker mutation,
Kilo/OpenCode receiver/model execution, GPU, and ComfyUI remain off.

Windows API references for the future handle observer:

- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/en-us/windows/desktop/api/winbase/nf-winbase-getfileinformationbyhandleex
- https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info
- https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-point-operations

Dedicated inert tests: 42/42. The working-tree adjacent matrix passed
120/120. Staged-only and committed-tree results are recorded in the
checkpoint handoff after the commit.
