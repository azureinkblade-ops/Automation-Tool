# EA-4E.92WP Buildx job-limit candidate

Status: SOURCE-LEVEL CANDIDATE / NATIVE LAUNCHER HOLD.

`prepare_buildx_job` accepts explicit, bounded process-count, per-process
memory, and total-job-memory limits. It configures the existing kill-on-close
and active-process flags plus the total-memory flag, then requires exact
readback before returning the owned job handle. Invalid requests are denied
before creating a job; configuration/readback failures follow the existing
owned-handle cleanup and unknown-cleanup path. The original one-process
`prepare_job` behavior is preserved. Focused synthetic tests passed (135),
including no-breakaway flags and retained-handle cleanup uncertainty.

This is job preparation, not process-tree containment. No process is created
or assigned. A later launcher must prove creation-time job membership,
non-breakaway behavior, retained-handle ownership, termination and zero
active members under a hard deadline, bounded output, stable plugin identity,
and independent local builder/daemon identity. Fake tests do not qualify
Windows API behavior. The current `DockerCli` does not call this helper.

Windows job-object process-tree and kill-on-close semantics:
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
Windows job memory and limit-flag semantics:
https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information

No native job API, Docker, Buildx, model, GPU, receiver, handoff, or
production action ran. Native and production gates remain HOLD.
