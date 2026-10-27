# EA-4E.92TZ local-log-only non-model control candidate

Date: 2026-10-27
Status: SOURCE CANDIDATE / NATIVE HOLD

The current-host 92TY small-envelope control passed once with Docker logging
disabled. The 92TV larger-envelope start failed with exit 128; the cause
remains unclassified. This candidate changes the 92TY control's logging
setting only: `--log-driver=local --log-opt max-size=16k --log-opt max-file=1`
instead of `--log-driver=none`. It retains the image, `--network none`, zero
mounts and published ports, no GPU assignment, read-only root, explicit
`NVIDIA_VISIBLE_DEVICES=void`, 256 MiB memory/swap, one CPU, 16 PIDs,
16 MiB `/tmp` tmpfs, restart disabled, `/bin/sh -c 'sleep 45'`, and the
same Bash, cat, loopback, and expected-refused localhost checks.

The variant has its own owner prefix and checks the requested logging
configuration in the pre-start inspect. It uses the existing exact-owner
cleanup and absence confirmation. Docker's requested 16 KiB one-file log
settings do not establish a hard disk bound or zero retention before
confirmed removal. No raw container log is read by this probe.

Focused strict non-live fake tests passed (90/90), including the new
logging success, pre-start mismatch denial, failed-start cleanup, and
unreviewed-mode denial. These tests do not qualify a native run. The
candidate requires one new independent read-only review of the pinned
committed runtime and a separate exact one-shot native authorization.
Neither approval is inherited from 92TY. No Docker container, Ollama server,
model, GPU, receiver, or agent handoff ran for this candidate. Production
remains HOLD.
