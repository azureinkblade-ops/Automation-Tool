# EA-4E.92UD json-file log control candidate

Date: 2026-10-27
Status: SOURCE-ONLY CANDIDATE / NATIVE HOLD

The current-host small non-model Bash control passed with logging disabled.
The same envelope with Docker `local` logging failed at container start; the
cause remains unclassified. This source-only candidate compares Docker's
`json-file` logging driver with the same requested one-file `max-size=16k`
and `max-file=1` settings. Relative to the passing small control, logging
and the exact-owner prefix are the only create-argument changes. The image,
`--network none`, zero mounts and ports, no GPU assignment, read-only root,
`NVIDIA_VISIBLE_DEVICES=void`, 256 MiB memory/swap, one CPU, 16 PIDs,
16 MiB `/tmp` tmpfs, disabled restart, `/bin/sh -c 'sleep 45'`, and the
Bash/cat/loopback/expected-refused localhost checks are retained.

The variant checks the effective `json-file` log configuration before
start, and retains exact-owner cleanup and absence confirmation. The
requested log options do not prove a hard disk or retention bound; no raw
container log is read. Focused strict non-live fake tests passed (96/96),
including success, pre-start mismatch denial, failed-start cleanup, and
invalid-mode denial. These tests do not establish native behavior.

One new independent read-only review of the pinned committed source and
a separate exact one-shot native authorization are required before any
run. Neither the prior review nor the consumed 92TZ native approval
carries forward. No Docker container, Ollama server, model, GPU, receiver,
or agent handoff ran for this candidate. Production remains HOLD.
