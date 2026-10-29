# EA-4E.92VJ quiet image-ID parser candidate

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW REQUIRED / NATIVE HOLD

A fail-closed parser now accepts only one canonical `sha256:` image ID
with an optional single line ending from a future bounded Buildx
`--quiet` stdout capture. It rejects extra lines, whitespace, uppercase
or shortened digests, non-bytes, invalid bytes, and overlong output.
Strict synthetic/source regressions passed (160/160). No Docker, model,
GPU, receiver, handoff, or production action ran.

This parser does not establish the native Buildx output contract or
image trust. A future launcher must cap stdout and stderr while the
process runs, require successful exit, parse only the bounded stdout,
then inspect the exact image ID and verify its platform and six model
files. It must also prove local builder and base-image identity,
pre-start process containment, deadline/cleanup, and daemon-side
reconciliation. Independent source review remains required. Production
remains HOLD.
