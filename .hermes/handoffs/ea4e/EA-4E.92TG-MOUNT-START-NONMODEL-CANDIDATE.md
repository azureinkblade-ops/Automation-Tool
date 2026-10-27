# EA-4E.92TG mount/start non-model candidate

Date: 2026-10-27

92TF failed at Docker start with `exit_code=128`, `oom=false`, and an
unclassified fixed category. The cause is unknown. The earlier 92SA
non-model probe started the same pinned image successfully, but used no
model mount and a smaller resource envelope. A read-only `docker info`
query after 92TF reported Linux/amd64 Docker Engine 29.6.2, cgroup v2,
and 16,637,886,464 bytes of daemon memory. The 20 GiB container limit
exceeds that reported memory; this is an observation, not proof of the
start failure's cause or proof that Docker rejects the limit.

This source-only candidate adds an opt-in `mount_only_probe` mode and a
separate one-shot entrypoint. It reuses the reviewed image identity,
six-file host model inventory, exact-owner checks, network-none and
read-only mount, 20 GiB/four CPU/64 PID limits, 2 GiB tmpfs, requested
one-file 16 KiB Docker-local logging, fixed-category failure output,
deadlines, and exact cleanup. It substitutes `/bin/bash -c 'sleep 60'`
for `/bin/ollama serve`, checks only the `lo` interface, and returns
before any HTTP request. It never reads the mounted model files in the
container, invokes Ollama, or performs inference. No GPU is assigned.

Focused strict non-live tests passed 73/73, including entrypoint
isolation, successful mount/start path, failed-start category, no HTTP,
and cleanup fakes. No Docker, model, GPU, receiver, or handoff call ran
for this candidate. Fake tests do not qualify native behavior. The
committed candidate needs independent read-only review and separate
exact one-shot native authorization before any run. Production remains
HOLD.
