# EA-4E.92SL read-only manifest-root candidate

Date: 2026-10-26

The 92SK one-shot tags-only diagnostic returned a fixed
`read_only_filesystem` category at `/api/tags`. No inference ran, cleanup
completed, and its authorization is consumed.

Static inspection of Ollama's current upstream source shows that the tags
model-list path calls `manifest.Manifests(true)`. That function obtains both
the v2 and legacy manifest roots. Its path helper calls `os.MkdirAll` for
each root. The six-file staged `qwen3:14b` tree had `manifests` and `blobs`,
but no `manifests-v2` directory. A missing v2 directory on a read-only bind
mount is a plausible explanation of the observed category, not proof about
the exact pinned image or its specific error text.

Source: https://github.com/ollama/ollama/blob/main/server/model_list.go and
https://github.com/ollama/ollama/blob/main/manifest/paths.go

One empty `manifests-v2` directory was added to the ignored staged-model
root, without changing, deleting, or rewriting any model file. The staged
file-inventory validator accepted the same six pinned files and directory
tree; the new directory was independently checked empty. No container,
model, GPU, receiver, or handoff ran for this preparation.

The pinned launcher/runtime source remains unchanged from the 92SJ reviewed
commit. A new exact one-shot authorization, a fresh stage revalidation, and
read-only old-container absence check are required before any native
tags-only test of this hypothesis. A successful tags response would still
not qualify inference or production. Production remains HOLD.
