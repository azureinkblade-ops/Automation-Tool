# EA-4E.92WB Isolated Buildx discovery design

Date: 2026-10-31 (America/Phoenix)
Status: SOURCE ASSESSMENT / NO NATIVE SETUP OR RUN

The 92VZ direct-executable probe remains on independent-review HOLD. Existing
EA-4E Windows job/AppContainer modules are partial and do not supply a proven
launcher with creation-time process-tree, filesystem, and Docker-state bounds.
Do not invoke 92VZ or treat those partial modules as a containment wrapper.

Docker CLI v29.6.2 source derives its Windows default system plugin directory
from the `ProgramFiles` environment variable, and its plugin listing may
validate multiple candidates. The restricted 92RM transport supplies only
`SYSTEMROOT`, while read-only host inspection found 15 installed plugin
executables in the real system directory. Restoring the real `ProgramFiles`
value would therefore broaden executable discovery beyond pinned Buildx.

Candidate next route: prepare a new private, empty Docker config directory and
a separate private fake `ProgramFiles/Docker/cli-plugins` tree containing only
one hash-verified Buildx copy. Point a command-specific transport at those
directories, use the already pinned Docker CLI and explicit local npipe host,
and deny any other executable candidate or mutable path. This is a design, not
an approved implementation. Before native use it needs source and ACL review,
exact file identity and no-replacement evidence, bounded process-tree cleanup,
redacted output handling, Docker-locality proof, focused tests, independent
review, and a new one-shot authorization. Copying the plugin or creating the
directory has not been approved or performed in this checkpoint.

No Docker/Buildx executable, container, archive upload, build, model,
GPU, receiver, agent handoff, or production action ran. The private model
archive and preserved Docker runtime directories remain untouched. All native
build, model, handoff, and production gates HOLD.

Sources:
- https://github.com/docker/cli/blob/v29.6.2/cli-plugins/manager/manager_windows.go
- https://github.com/docker/cli/blob/v29.6.2/cli-plugins/manager/manager.go
