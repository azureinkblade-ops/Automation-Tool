# EA-4E.92WX Buildx job-owner token candidate

Status: SOURCE-LEVEL CANDIDATE / NATIVE LAUNCHER HOLD.

`prepare_owned_buildx_job` wraps a verified Buildx job handle in a token
that permits one creation-owner claim. The Buildx creation-resource factory
now requires that token instead of a bare handle and checks it against the
one-job attribute list. A second attribute set cannot claim the same token.
Once claimed, the token denies independent close and permits only its
creation owner to close it after process and attribute cleanup. Uncertain
job cleanup is not retried. The original raw `prepare_buildx_job` helper
remains unchanged for existing callers. Focused and adjacent injected tests
passed (156).

This does not prevent a caller from directly closing a raw handle through
the underlying API, or wrapping one raw handle in two different tokens. It
does not prove native job membership, child termination under a hard
deadline, zero active job members, bounded output, plugin identity through
load, or independent local builder/daemon identity. No native process,
Docker, Buildx, model, GPU, receiver, handoff, or production action ran.
Native and production gates remain HOLD.
