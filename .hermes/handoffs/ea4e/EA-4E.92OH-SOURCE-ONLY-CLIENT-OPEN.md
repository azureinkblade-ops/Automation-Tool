# EA-4E.92OH source-only limited-client open candidate

Status: NON-LIVE SOURCE-ONLY / NO NATIVE CLIENT OPEN.
Governing parent: `4163a4e3090576c7077af71196b3dc1df1abfe2a`.

The candidate recognizes only the creator's ceremony-plus-random pipe name
shape, with two distinct nonzero canonical GUIDs. Name shape is not a trusted
announcement binding or a secret. For a future separately authorized native
call it requests exactly one 92OG access mask with `CreateFileW`, no generic
fallback, no sharing, and `OPEN_EXISTING`. An unexpected success on a
negative probe closes the returned handle and denies; a specific-write
success only retains the handle for later same-handle checks and does not
authenticate a frame or client identity.

The fixture exposes only an inert name-shape path. It has no CLI route to
native `Open`; tests never create or connect to a pipe. The working-tree
dedicated and adjacent matrix passed 156/156; the staged source export
passed 8/8. Medium-token provenance,
announcement binding, actual access checks, canonical message transfer,
and trusted issuer installation remain open. No Docker mutation, receiver,
model, credential, GPU, ComfyUI, or production activation occurred.
