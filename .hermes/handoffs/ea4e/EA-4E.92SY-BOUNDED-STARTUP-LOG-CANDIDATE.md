# EA-4E.92SY bounded startup-log candidate

Date: 2026-10-26

The 92SX native probe established an Ollama exit code of 1 without OOM,
but logging was disabled and the cause remains unknown. This source-only
candidate adds a separate opt-in tags-only startup diagnostic entrypoint.
The existing entrypoint remains on `--log-driver=none` and its runtime
behavior is unchanged unless the diagnostic flag is set.

The diagnostic requests Docker's local log driver with one 16 KiB file,
checks that exact configuration before start, and reads at most 4096 bytes
from one `docker container logs --tail 20` call only after an exact-owned
stopped-process finding. It maps byte patterns to fixed categories:
`read_only_filesystem`, `permission_denied`, `missing_path`,
`storage_full`, `unclassified`, or `unavailable`. It never prints raw
Docker logs. The category is a hint, not proof of cause. The existing
network-none, read-only model mount, localhost-only server, no GPU,
resource limits, deadline, and exact-owned cleanup remain. The diagnostic
mode refuses a non-tags-only run.

Docker's local logging driver stores container output in daemon-managed
local files. The one-file 16 KiB cap and exact-owned container removal
limit this added side effect, but do not prove forensic zero-retention.
No credentials, private prompt, receiver, or inference are
part of this candidate. Source basis for the driver options and log read:
https://docs.docker.com/engine/logging/drivers/local/ and
https://docs.docker.com/reference/cli/docker/container/logs/ .

Focused strict non-live tests passed 62/62, including opt-in isolation,
bounded log options, fixed-category classification, traceback redaction,
and refusal of inference. No Docker, Ollama, model, GPU, receiver, or
handoff ran for this candidate. It requires independent source review and
separate exact native authorization that explicitly accepts transient
daemon-local logging before any run. Production remains HOLD.
