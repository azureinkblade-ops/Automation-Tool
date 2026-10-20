# EA-4E.92OX attestation-to-record value binding

Status: NON-LIVE VALUE COMPARISON / CHANNEL AND HANDLE AUTHORITY HOLD.
Governing parent: `55642df6669589bb87dd7526b777b676511e2d76`.

The pure `ea4e92ox_attestation_record_binding` helper compares a parsed
creator claim to the medium coordinator's supplied retained-record
observation. It requires the claimed and observed volume/file IDs to match,
compares SHA-256 over the exact bounded record bytes, and runs the v2
announcement decoder against the independently pinned ceremony and launch
expectations. Trailing bytes, changed identity, changed content, malformed
v2 syntax, stale time, and mismatched nonce fail closed. The focused v2,
attestation, and binding matrix passed 94/94.

This comparison proves no native fact by itself. The caller must establish
that the claim came from the authenticated elevated creator on the same
one-shot connection, that the medium observation came from the retained
file handle with EOF and pre/post metadata checks, and that both process
and file identities remained stable. The descriptor hashes remain creator
claims until separately qualified readback and installer policy comparison.
No actual file, pipe, process, receiver, model, Docker, GPU, ComfyUI, or
production action occurred. Full 92NK, issuer authority, and production
remain HOLD.
