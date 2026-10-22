# EA-4E.92RB Docker Service Access Hold

Status: APPROVED SINGLE ATTEMPT CONSUMED / OPERATOR ELEVATION REQUIRED.
Source baseline: `38229b4fdbc4283301406e81d0d9eb2d44f08728`.

The operator approved one new service-and-Desktop start attempt after 92RA,
acknowledging the restart-policy-container risk. `Start-Service
com.docker.service` failed before Desktop launch because this process could
not open the service. No second service or Desktop start was attempted.

Read-only checks showed `com.docker.service` still STOPPED, demand-start,
with no PID. The calling token is Medium Mandatory Level; its Administrators
group is deny-only. WSL itself reported version 2 and a running WslService.
This is evidence of an elevation boundary, not a diagnosis of why the
earlier Desktop process exited or of Docker image/container state.

The approved attempt is consumed. An operator must complete a separately
governed UAC-elevated Docker start before daemon/image/container inspection
can continue. No EA-4E container, receiver, model, credential, GPU,
ComfyUI, or production action occurred in this checkpoint. Local-container
qualification and production remain HOLD; strict 92AT remains REJECT.
