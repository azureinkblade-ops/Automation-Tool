# EA-4E.92WT Buildx startup-info candidate

Status: SOURCE-LEVEL CANDIDATE / NATIVE LAUNCHER HOLD.

`prepare_buildx_startup_info_ex` reuses the existing value-only
`STARTUPINFOEXW` layout and the reviewed one-job attribute ownership
validator. It sets `StartupInfo.cb` to the structure size, points
`lpAttributeList` at the owned attribute buffer, and retains the prepared
attribute owner. The existing AppContainer startup-info preparer is
unchanged. The focused synthetic suite passed (46).

Microsoft documents `STARTUPINFOEXW` as the extended structure used with
`CreateProcessW` and specifies `cb = sizeof(STARTUPINFOEX)`:
https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-startupinfoexw

This candidate does not call `CreateProcessW`, prove that Windows accepts
the layout or job attribute, or connect to `DockerCli`. The caller must
retain the attribute list and job handle through child cleanup. Native
creation-time containment, a hard deadline and zero active job members,
bounded output, plugin identity through load, and independent local
builder/daemon identity remain unproven. No native API, Docker, Buildx,
model, GPU, receiver, handoff, or production action ran. Native and
production gates remain HOLD.
