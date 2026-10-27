# EA-4E.92TT GPU-hidden non-model exit-128 HOLD

Date: 2026-10-27

David authorized exactly one native GPU-hidden, no-mount, non-model probe at
source `536d6a4f7d7922a6a5fac5503034a33962516a7f`, with runtime unchanged
from independently reviewed `8b09071ea7b527d537af02878b031e497f2fa922`.
Entrypoint, runner, and Docker CLI hashes matched; the six-file model stage
validated on the host; the pinned image ID matched; and no old `ea4e92tq-`
container existed.

The single run failed at `docker container start` with fixed output
`exit_code=128 oom=false startup_category=unclassified`. It had no model
mount, no GPU assignment, and explicitly set `NVIDIA_VISIBLE_DEVICES=void`.
The sleeping Bash command did not start. No loopback check, HTTP, Ollama
server, inference, receiver, or handoff ran. Exact-owner cleanup completed;
a separate read-only query found no residual 92TQ container. No retry
occurred. The one-run authorization is consumed.

The result does not support a simple explanation based solely on the model
mount, 20 GiB memory ceiling, Ollama startup, or inherited NVIDIA visibility.
The cause remains unknown. The fixed-category classifier did not identify
the Docker start error, so further one-variable containers would be poorly
informed. A separately governed, bounded diagnostic of Docker's start-error
evidence is the next meaningful boundary. Do not run another container,
model, receiver, GPU, or production activation under this authorization.
Production remains HOLD.
