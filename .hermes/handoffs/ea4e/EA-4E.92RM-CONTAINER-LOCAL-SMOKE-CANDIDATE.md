# EA-4E.92RM Container-Local Smoke Candidate

Status: NON-LIVE CODE CANDIDATE / NATIVE AND MODEL HOLD.
Predecessor: `fd6ff33c4506cc204c63b5d1ae228432a9ed1a68` (92RL).

`tools/ea4e92rm_container_smoke.py` is an opt-in, single-shot candidate
for a Docker-local `qwen3:14b` smoke. It has no command-line entry point.
No function in it was called with a real Docker client in this checkpoint.

The plan requires a digest-pinned image and image ID, exact Docker CLI
hash, fresh ceremony UUID, and a dedicated read-only model directory
containing only the six 92RJ-identified manifest/blob files. Its created
container requests `--network=none`, no host port, a read-only root,
read-only model mount, bounded tmpfs, 20 GiB memory and swap, 64 PIDs,
four CPUs, dropped capabilities, no new privileges, disabled logging,
and no restart. It inspects effective settings before starting the server.
An in-container interface check must show only `lo`, followed by a
container-local HTTP version check. Only then may one synthetic generate
request be sent. The CLI output is incrementally capped, the work budget
is 90 seconds within a 120-second total deadline, and the exact owned
container is stopped and checked in `finally`. No automatic container
deletion is performed.

Two independent read-only reviews of earlier working versions identified
unrelated-container cleanup, incomplete effective-setting checks, an
incomplete model inventory, deadline/output-cap gaps, and unverified-ID
cleanup. The current version adds random per-attempt ownership labeling,
pre-kill ownership verification, exact six-file inventory with walk-error
denial, before/after model hashes, aggregate output cap, and targeted
fake-only regressions. A fresh review of the committed version is still
required; these fixes are not self-attestation.

Focused fake-only result: 12 passed under the repository's live-side-effect
barrier. This does not prove Docker behavior, network isolation, Ollama
compatibility, model execution, GPU policy, or cleanup after daemon failure.
The default host model directory may contain unrelated files and therefore
cannot be mounted as-is. No compatible digest-pinned Linux image containing
`/bin/ollama`, `/bin/cat`, and `/usr/bin/curl` has been admitted. A read-only
Docker image query was denied by the current sandbox. The candidate has no
authorization to create a container, pull/build an image, invoke a model,
or perform an agent handoff. Production remains HOLD.
