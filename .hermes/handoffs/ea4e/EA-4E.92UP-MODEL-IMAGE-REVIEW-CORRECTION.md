# EA-4E.92UP model-image review correction

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW REQUIRED / NATIVE HOLD / PRODUCTION HOLD

This checkpoint responds to the one approved 92UO independent review of
`a9184fcb7e19886734cc130502fe19897d651a44`. The review returned HOLD.

The context writer now records device/inode identity during its pre-stream
inventory and compares it with the opened handle, alongside type and size.
The Dockerfile now checks `find` command status through shell assignments,
requires the five expected directories and their count, rejects entries
that are neither regular files nor directories, and checks the six pinned
file hashes. These are source-level safeguards, not evidence that the
pinned base can execute the recipe.

The writer remains streaming: a late read or hash failure can leave a
partial tar in the caller's output. A future launcher must use a discardable
staging artifact or an equivalent abort/reconcile protocol before connecting
it to Docker. Path and content races outside the opened file handle, Docker
build side effects, utility availability, and resulting image identity
remain unverified. Do not treat the pre-open identity check as an atomic
snapshot of the entire model tree.

Focused strict fake/source tests passed (122/122). No real model bytes were
streamed, and no Docker build, container, model, GPU, receiver, handoff, or
production activation occurred. A new independent read-only review and
separately governed native build authorization are required. Production
remains HOLD.
