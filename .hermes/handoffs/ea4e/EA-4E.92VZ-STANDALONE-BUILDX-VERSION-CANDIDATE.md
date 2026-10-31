# EA-4E.92VZ Standalone Buildx version candidate

Date: 2026-10-31 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW AND NATIVE RUN HOLD

The pinned Docker CLI v29.6.2 does not advertise Buildx under the restricted
environment, while the installed Buildx binary is present and hash-pinned.
Version-matched Docker CLI source derives the Windows system plugin directory
from `ProgramFiles`, which the restricted launcher omits. The same source can
enumerate and validate other plugin candidates. Restoring `ProgramFiles` to
that launcher would broaden executable discovery beyond the pinned Buildx
binary, so that is not proposed as the next native step.

Docker documents a standalone Buildx mode that invokes its binary directly.
`tools/ea4e92vz_buildx_version_probe.py` is a source-only candidate for one
value-only `version` probe of an exact SHA-256-pinned `docker-buildx.exe`.
It supplies only `SYSTEMROOT`, no Docker host/config, captures at most 4096
combined bytes, waits at most 15 seconds after process start, kills the exact
process on timeout/overflow, and returns only success or a fixed denial.
It does not request a builder inspection, build, model, or daemon operation.
The pre-launch hash and process descendants are not hard-wall bounded; a
reviewer must assess those limits and error paths before any native run.

Seven focused synthetic tests passed with the repository live-test setup
excluded; the first test attempts were blocked by an unwritable sandbox temp
location, and a unique workspace test directory was used without deleting any
existing files. No Buildx executable, Docker daemon, container, archive,
model, GPU, receiver, handoff, or production action ran.

Sources:
- https://github.com/docker/cli/blob/v29.6.2/cli-plugins/manager/manager_windows.go
- https://github.com/docker/cli/blob/v29.6.2/cli-plugins/manager/manager.go
- https://docs.docker.com/build/ci/github-actions/configure-builder/#standalone-mode
