# EA-4E.92JJ bounded Docker inspect runner

Status: READ-ONLY IMAGE SMOKE PASS / NO CONTAINER OR RECEIVER START.
Governing predecessor: `65e26cf1936d990327e7209259e0a70a2132553c`.

An opt-in process runner now admits only the 92JI Docker inspect argv for
an exact container ID, network ID, or Linux/amd64 image index on the explicit
local engine pipe. It rehashes the executable, requires an existing empty
Docker config directory, strips the ambient Docker environment, supplies
an absolute executable and fixed working directory, and uses no shell.
Its two output readers retain at most 1 MiB stdout and 4 KiB stderr;
overflow kills the owned process. A five-second wait timeout kills the
owned process. Any stderr, nonzero exit, capture error, or unfinished reader
denies. The class is not wired into the app or container owner.

The dedicated fake-process suite passed 10/10. The adjacent fake-only
ladder passed 314/314 before commit. One read-only current-daemon smoke
through this runner and the 92JI client returned the pinned Linux/amd64
manifest from the pinned index. The isolated Docker config directory
remained empty. No container was created or started, and no Kilo/OpenCode
receiver, provider/model, GPU, or ComfyUI was invoked.

The runner kills only its immediate owned CLI process; it does not provide
Windows Job Object process-tree containment. It does not establish that a
fresh, recorded receiver container exists or matches the provisional spec.
The original strict 92AT mapped-byte proof is separate. Production and
receiver launch remain HOLD.
