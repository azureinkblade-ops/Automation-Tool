# EA-4E.92OQ v2 announcement binding design

Status: NON-LIVE DESIGN / IMPLEMENTATION AND NATIVE QUALIFICATION HOLD.
Governing parent: `189a85b2f0c5bc42994d53fcf93d99440af46e69`.
Profile: accepted 92DE trusted local-container host only; strict 92AT remains separate.

## Decision

Keep the 92OJ v1 decoder unchanged. A record containing `version: 2` must
continue to fail its exact-field check. A separately named v2 decoder may be
implemented after this contract is reviewed. A v2 JSON field is a claim, not
proof of who created the file or what descriptor was observed. The coordinator
must not turn creator-supplied values into independent expectations.

The proposed v2 record retains all v1 identity, nonce, pipe-name, and time
fields, and adds `record_volume_serial` and `record_file_id` from the trusted
elevated creator's retained record handle. Both are fixed-width lowercase hex
encoding of the Windows `FILE_ID_INFO` values; zero identity is denied. The
creator must observe these after the final write/flush, then keep that same
handle open. The record has a 1024-byte canonical ASCII JSON limit, exact
field set, no duplicates, and no trailing bytes. Because the record cannot
contain its own final content hash without circularity, its content hash is
reported separately over the exact flushed bytes.

An independently authenticated creator attestation must carry the ceremony
ID, coordinator nonce, creator process identity, record volume/file ID, exact
record SHA-256, and a digest of the creator-observed owner/group/DACL/SACL/
label descriptor. The creator obtains the descriptor from the retained file
handle with `ACCESS_SYSTEM_SECURITY` and scoped `SeSecurityPrivilege`; the
medium coordinator does not attempt a SACL/label read. The attestation must
also bind an installer manifest identity for the already installed directory
and the issuer executable digest. The attestation channel and independent
installer manifest are not yet implemented or qualified. A JSON copy of this
attestation inside the record would not satisfy the channel requirement.

The medium coordinator must retain its launch/process handle and the opened
directory and record handles. It compares the process PID and creation time
against its own launch observation, compares the record's `FILE_ID_INFO` to
the creator attestation and its own retained file handle, checks owner/DACL
and actual limited-token read/denied-mutation rights, and reads exact bytes
with EOF and pre/post handle metadata checks. It verifies the record digest
against the authenticated creator attestation. Any mismatch, missing label
attestation, unknown installer manifest, privilege failure, uncertain handle
identity, or process exit/drift is HOLD, not a fallback to v1.

The coordinator's fresh nonce must reach the trusted creator through an
independently authenticated channel before record creation. No request field,
environment value, per-user file, or unauthenticated pipe is an acceptable
nonce authority. The channel's endpoint authentication, transcript binding,
and replay behavior remain open. A durable ledger must atomically consume
ceremony ID, nonce, record identity, and creator attestation hash before any
pipe client connection. The process-local 92OK lease is not sufficient.

## Qualification order

1. Source-review and test a v2 canonical parser separately from v1. Reject
   malformed fixed-width IDs, duplicate fields, drifted identity, and time
   violations. Parser tests prove syntax only.
2. Source-review elevated retained-handle file descriptor and `FILE_ID_INFO`
   readback, plus medium owner/DACL and identity comparison. Do not expose a
   native mode until there is a bounded probe authorization.
3. Independently qualify the installer manifest and authenticated nonce and
   attestation channels, including restart-safe one-shot accounting.
4. With pinned source, binary, operator, ceremony, deadline, and cleanup,
   seek a new exact authorization for one inert native file/limited-client
   qualification. No previous one-shot authorization may be reused.

No namespace was installed, no pipe or file was opened, and no receiver,
model, Docker mutation, GPU, ComfyUI, or production action was authorized by
this design. Full 92NK, trusted issuer, real agent communication, and
production remain HOLD.

Primary API references:

- https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info
- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control
