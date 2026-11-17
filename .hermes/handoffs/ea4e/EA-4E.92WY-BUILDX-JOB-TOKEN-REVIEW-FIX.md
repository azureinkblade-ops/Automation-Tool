# EA-4E.92WY Buildx job-token review fix

Status: SOURCE-LEVEL REVIEW FINDINGS REPAIRED / NATIVE LAUNCHER HOLD.

One independent, read-only review of committed 92WX `7cf9063` found two
source-level gaps. `OwnedBuildxJob` could be constructed without verified
job preparation, and the publicly available creation-owner object could be
passed to `job.close(owner)` before process and attribute cleanup. The
one-review authorization is consumed. The reviewer ran no tests or native
actions.

The token constructor now requires a module-private preparation proof that
only `prepare_owned_buildx_job` supplies after job-limit readback. A claimed
token refuses close unless its creation owner is in cleanup, its attributes
are closed, and any attached process owner is closed. The existing raw job
preparer is unchanged. Focused and adjacent injected tests passed (157).

This is a source-level invariant for ordinary callers, not a security
boundary against introspection, direct underlying API calls, or two tokens
constructed for one raw handle. Native job membership, hard-deadline child
termination, zero active job members, bounded output, plugin identity
through load, and independent builder/daemon locality remain unproven. No
native process, Docker, Buildx, model, GPU, receiver, handoff, or production
action ran. Native and production gates remain HOLD.
