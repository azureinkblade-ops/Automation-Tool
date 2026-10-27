# EA-4E.92TW non-model control-envelope comparison

Date: 2026-10-27
Status: SOURCE AND READ-ONLY COMPARISON / NATIVE HOLD

The 92SA non-model Bash transport probe succeeded once. Its committed
runtime blob is unchanged from reviewed commit `2bac5423291337b8579a0e4841cd49833b51ef4c`
through HEAD `0e318707bd30cb818cea724e9f78b4eef4b5f2c1`; its entrypoint
blob is also unchanged from the approved 92SA source commit
`710bca4ec5dcf53b88e52b689325ab7389acc1f5`. The entrypoint SHA-256 is
`d21a02ec828ca05d11ae99e01da9fa0b55885257a66ab3e2f6dd8ba135ca6883`.
The probe imports the shared Docker CLI client, which has changed since 92SA;
this comparison is not a fresh independent review of the current import graph.

The 92SA successful envelope used `--network none`, zero model mounts, no
published port or GPU assignment, read-only root, `NVIDIA_VISIBLE_DEVICES=void`,
256 MiB memory/swap, one CPU, 16 PIDs, 16 MiB `/tmp` tmpfs, Docker log
driver `none`, and `/bin/sh -c 'sleep 45'`. It then checked Bash availability and a
refused localhost connection from inside the running container. The recent
92TV failed-start envelope instead used 8 GiB memory/swap, four CPUs, 64
PIDs, 2 GiB `/tmp` tmpfs, Docker's local log driver, additional Ollama
environment variables, and `/bin/bash -c 'sleep 60'`. Both used the same
pinned image, no model mount, and no GPU assignment.

A bounded read-only Docker info query reported Linux/x86_64, 16,637,886,464
bytes of daemon memory, default runtime `runc`, default log driver
`json-file`, and `local` among advertised log plugins. These fields do not
prove that the 92TV envelope can start or identify its exit-128 cause.

The next evidence-producing native control would requalify the previously
successful 92SA envelope once on the current host, with no model. A pass
would support an envelope-difference hypothesis; a failure would point to
a changed host/daemon baseline without proving its cause. This is a proposal,
not authorization. The current import graph needs independent read-only
review, and a new exact bounded one-shot authorization is required before
any control run. No container, model, GPU, receiver, or handoff was started
for this comparison. Eight focused strict non-live fake tests passed against
the current import graph; they do not qualify a native rerun. Production
remains HOLD.
