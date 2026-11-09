# EA-4E.92WQ Buildx job-attribute candidate

Status: SOURCE-LEVEL CANDIDATE / NATIVE LAUNCHER HOLD.

`prepare_buildx_job_attributes` composes a one-entry `JOB_LIST` creation
attribute from an explicitly supplied job handle. It retains the backing
array until attribute-list cleanup and rejects invalid handle values or the
existing two-attribute AppContainer profile before allocation. The existing
AppContainer `JOB_LIST` plus `SECURITY_CAPABILITIES` profile is unchanged.
The focused synthetic adapter suite passed (129).

This does not configure or prove the supplied job handle, create a process,
or connect the attribute list to `DockerCli`. The caller must retain the job
handle until list cleanup. Creation-time child job containment, hard-deadline
termination with zero active members, bounded output, plugin identity through
load, and independent local builder/daemon identity remain unproven. Fake
tests do not qualify native Windows API behavior.

Windows documents `PROC_THREAD_ATTRIBUTE_JOB_LIST` as a creation-time list of
job handles and requires attribute-list storage to remain valid until deletion:
https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute

No native job API, Docker, Buildx, model, GPU, receiver, handoff, or
production action ran. Native and production gates remain HOLD.
