# EA-4E.92TL reduced-memory non-model exit-128 HOLD

Date: 2026-10-27

David authorized exactly one native 92TJ reduced-memory non-model probe at
source commit `83d38cb058b5e23c89546e01bd4e2006b8fef7f4`, with runtime
unchanged from independently reviewed `473081b252f430aa37338364e45d6d5aa26ea711`.
Entrypoint, runner, and Docker CLI hashes matched the authorization; the
six-file staged qwen3:14b inventory validated; the pinned image ID matched;
and no previous `ea4e92tj-` container existed.

The one run failed at `docker container start` with fixed output
`exit_code=128 oom=false startup_category=unclassified`. The 8 GiB memory and
swap limits replaced the earlier 20 GiB limits; the read-only model-stage
mount and other containment remained. The sleeping Bash command did not
start. No loopback inspection, HTTP, Ollama server, model inference, GPU,
receiver, or agent handoff ran. Exact-owner cleanup completed, and a separate
read-only Docker query found no residual 92TJ container. No retry occurred;
the one-run authorization is consumed.

The result makes a simple 20 GiB-only explanation insufficient, but does not
identify the start-failure cause. The shared mount, logging, tmpfs, daemon
policy, or another start factor may still matter. Any next native isolation
requires a new bounded design, independent review, and exact authorization.
Production remains HOLD.
