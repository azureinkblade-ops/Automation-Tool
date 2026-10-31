# EA-4E.92WC Isolated Buildx layout candidate

Date: 2026-10-31 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / REVIEW AND NATIVE SETUP HOLD

`tools/ea4e92wc_isolated_buildx_layout.py` is a value-only preflight for the
92WB design. It requires an empty config directory, a private fake
`ProgramFiles/Docker/cli-plugins` tree containing exactly one plain
`docker-buildx.exe`, and the expected SHA-256. It denies reparse points on
those immediate layout components and returns only `SYSTEMROOT`,
`DOCKER_CONFIG`, and `ProgramFiles` environment values. It performs no copy,
ACL change, Docker call, plugin execution, or cleanup.

Five focused synthetic tests passed with the repository live-test setup
excluded. This is not a complete security boundary: it does not prove private
ACLs or ancestor path identity, prevent replacement after validation, bind a
process tree, prove local Docker endpoint use, or verify that a native Buildx
command is read-only. A reviewed setup/launcher, exact authorization, and
native evidence remain separate gates. The 92VZ standalone probe remains on
independent-review HOLD and must not be run.

No Docker/Buildx executable, container, archive upload, build, model,
GPU, receiver, agent handoff, or production action ran. The private model
archive and preserved Docker runtime directories remain untouched. All native
build, model, handoff, and production gates HOLD.
