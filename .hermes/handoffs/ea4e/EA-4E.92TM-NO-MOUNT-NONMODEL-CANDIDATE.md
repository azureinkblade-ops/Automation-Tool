# EA-4E.92TM no-mount non-model candidate

Date: 2026-10-27

92TI and 92TL both failed at Docker start with fixed exit 128, using a
read-only model-stage bind mount at 20 GiB and 8 GiB respectively. The cause
remains unknown. The earlier 92SA Bash transport succeeded without a model
mount but also used a smaller resource envelope.

This source-only candidate isolates the bind mount. It keeps the pinned image,
8 GiB memory/swap, four CPUs, 64 PIDs, 2 GiB tmpfs, network-none, read-only
root, no GPU/published ports, sleeping Bash command, loopback check,
requested one-file 16 KiB Docker-local logging, fixed-category errors,
deadlines, and exact-owner cleanup. It omits only `--mount` and requires the
effective container inspect to report zero mounts. The distinct
`ea4e92tm-` name is permitted only when non-model mount-only and
reduced-memory flags are both enabled. The staged model inventory is still
validated on the host, but no model file is mounted into the container. No
HTTP, Ollama server, or inference path is reached.

Focused strict non-live tests passed 87/87, including success, failed start
and cleanup, unexpected-mount denial, invalid mode flags, and no inference.
Fakes do not establish native readiness. No Docker, model, GPU, receiver, or
handoff call occurred for 92TM. Independent committed-source review and a
separate exact one-shot native authorization are required. Production remains
HOLD.
