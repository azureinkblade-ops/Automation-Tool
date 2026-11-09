# EA-4E.92WR Buildx suspended-handoff candidate

Status: SOURCE-LEVEL CANDIDATE / NATIVE LAUNCHER HOLD.

`create_owned_buildx_suspended_process` accepts only an owned, open,
job-only attribute list with one retained job handle. It passes that list's
buffer to an injected suspended-creation collaborator and requires an exact
result with valid distinct process/thread handles and IDs, suspended state,
reported creation-time job binding, and no AppContainer binding. A denied
identity or predicate terminates and closes the returned handles through the
existing owned-process path; ambiguous creation or cleanup remains unknown.
The focused synthetic suite passed (92).

This is a value-level handoff, not a native process launcher. The injected
collaborator's predicates are unverified assertions, not proof of Windows
creation-time membership. No process is created or resumed by this module.
The caller still owns the prepared attributes and job handle. The module
is not connected to `DockerCli`, and the existing AppContainer path is
unchanged.

Native creation-time containment, hard-deadline termination and zero active
job members, bounded output, plugin identity through load, and independent
local builder/daemon identity remain unproven. No native job API, Docker,
Buildx, model, GPU, receiver, handoff, or production action ran. Native and
production gates remain HOLD.
