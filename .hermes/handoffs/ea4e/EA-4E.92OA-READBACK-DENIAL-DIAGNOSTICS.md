# EA-4E.92OA readback denial diagnostics

Status: NON-LIVE SOURCE-ONLY / NATIVE RETRY HOLD.
Governing parent: `94a04b24f6ef4cb2e81cd41f65b6cbb3c961653b`.

The approved 92NZ native readback-only attempt exited `15`, which identified
the readback stage but not the failing check. Its one-shot authorization is
consumed and its HOLD result remains unchanged.

This checkpoint separates `GetSecurityInfo` access denied, privilege not held,
other API error, null descriptor, invalid native descriptor, bounded descriptor
size, and structural screen denials into distinct nonzero process exits. A
readback-stage exception also has its own exit. The `--classify-readback` CLI
is an inert mapping test path; it neither opens a pipe nor adjusts privileges.
No result here establishes actual pipe security or limited-client access.

The focused source/descriptor/creator and adjacent protected-store regression
matrix passed 115/115 on the working tree. The source-only staged export
passed 25/25. No native mode, Docker mutation,
Kilo/OpenCode receiver, model, credential, GPU, ComfyUI, or production
activation was exercised. A new native run requires a separately authorized,
pinned source commit and executable hash with a fresh one-shot budget.
