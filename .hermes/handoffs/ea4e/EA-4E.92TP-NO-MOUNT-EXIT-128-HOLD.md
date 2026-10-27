# EA-4E.92TP no-mount exit-128 HOLD

Date: 2026-10-27

David authorized exactly one native no-mount, non-model probe at source
`1730f24e55e93cfd9ef58e9a929aea3cebe2acbf`, with runtime unchanged from
independently reviewed `8022c8eb7dcc76d6b495e74880e8d7b9c071f779`.
Entrypoint, runner, and Docker CLI hashes matched; the staged six-file model
inventory validated on the host; the pinned image ID matched; and no old
`ea4e92tm-` container existed.

The single run failed at `docker container start` with fixed output
`exit_code=128 oom=false startup_category=unclassified`. The container had
no model bind mount and the 8 GiB non-model resource envelope. The Bash
command did not start. No loopback check, HTTP, Ollama server, inference,
GPU assignment, receiver, or handoff ran. Exact-owner cleanup completed;
a separate read-only query found no residual 92TM container. No retry
occurred. The one-run authorization is consumed.

Removing the bind mount did not clear the start failure. A read-only image
inspect then showed its baked-in `NVIDIA_VISIBLE_DEVICES=all`, while the
earlier successful 92SA Bash transport explicitly set that variable to
`void`. This difference is a hypothesis only, not a proven cause. Other
differences include logging and resource limits. Any next native isolation
requires a new bounded design, independent review, and exact authorization.
Production remains HOLD.
