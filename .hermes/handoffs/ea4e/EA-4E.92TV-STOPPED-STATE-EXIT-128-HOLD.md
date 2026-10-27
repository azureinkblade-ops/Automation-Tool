# EA-4E.92TV stopped-state diagnostic exit-128 HOLD

Date: 2026-10-27

David authorized exactly one non-model Docker start diagnostic at source
`cce242d25d7bc8b605bf9e0bc9f711c8c3393648`, with runtime unchanged
from independently reviewed `37aace694c6819a9140a9b246cfa5d3e9d1466d2`.
Before the one run, the worktree was clean and the pinned entrypoint, runner,
and Docker CLI SHA-256 hashes matched the authorization. The runner validated
the six-file model stage on the host and the local image identity before
creating its exact-owned container. The model stage was not mounted.

The one probe failed at `docker container start` with fixed output
`exit_code=128 oom=false startup_category=unclassified`. The bounded
`State.Error` category, bounded Docker logs, and bounded CLI stderr did not
identify a cause. The Bash sleep command did not start. No loopback check,
HTTP, Ollama server, model inference, GPU assignment, receiver, or agent
handoff ran. The runner completed exact-owner cleanup, and a separate
read-only Docker query returned zero `ea4e92tq-` containers. No retry
occurred; the one-run authorization is consumed.

The repeated exit-128 start failure remains unexplained. Do not infer a root
cause from the fixed unclassified category. Further native Docker, model,
GPU, receiver, or production actions require separate governance. Production
remains HOLD.
