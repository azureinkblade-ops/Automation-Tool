# EA-4E.92TQ GPU-hidden non-model candidate

Date: 2026-10-27

The 92TM no-mount, 8 GiB Bash probe still failed at Docker start with fixed
exit 128. The cause is unknown. Read-only image inspect shows baked-in
`NVIDIA_VISIBLE_DEVICES=all`. The earlier successful 92SA Bash transport
explicitly used `NVIDIA_VISIBLE_DEVICES=void`, but it also differed in
resource limits, logging, and tmpfs size. The environment difference is a
hypothesis, not a diagnosis.

This source-only candidate keeps the 92TM pinned image, zero model mount,
8 GiB memory/swap, four CPUs, 64 PIDs, 2 GiB tmpfs, network-none, read-only
root, no GPU assignment or published ports, sleeping Bash command, loopback
check, requested one-file 16 KiB Docker-local logging, deadlines, fixed
categories, and exact-owner cleanup. It changes only the effective NVIDIA
visibility setting to `void`, verified in Docker inspect; `all` or missing
`void` fails before start. The new mode has a distinct `ea4e92tq-` name and
is permitted only with the non-model, reduced-memory, no-mount flags. No
HTTP, Ollama server, model-file mount, or inference path is reached.

Focused strict non-live tests passed 97/97, including success, failed start
and cleanup, effective GPU-visibility denials, invalid mode combination,
and no inference. Fakes do not establish native readiness. No Docker, model,
GPU, receiver, or handoff call occurred for 92TQ. Independent committed-source
review and a new exact one-shot native authorization are required. Production
remains HOLD.
