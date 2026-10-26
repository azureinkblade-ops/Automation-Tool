# EA-4E.92SX Ollama exit-one HOLD

Date: 2026-10-26

The user approved exactly one tags-only native diagnostic at source commit
`9bbae7910c77bcad185769720632f774da631746`. Fresh preflight matched
the authorized entrypoint, runner, and Docker CLI hashes; validated the
same six pinned qwen3:14b files and empty `manifests-v2` directory; and
found no old `ea4e92rm-` container.

The one invocation passed initial and post-start effective-containment
checks. Docker then rejected `/bin/cat /proc/net/dev`. The single bounded
state recheck found the exact-owned container stopped with exit code `1`
and `OOMKilled=false`. The launcher stopped before `/api/tags` or any
generate request. No inference, receiver call, agent handoff, GPU
assignment, or production activation occurred. Exact-owned cleanup
completed; a separate read-only Docker query found no remaining smoke
container. The one-shot authorization is consumed; there was no retry.

Exit code 1 is not a root-cause diagnosis. Logging was disabled by the
containment contract, and no server text was captured. The
empty-`manifests-v2` hypothesis remains untested. Do not relax read-only
mounts or other containment based on this result. Next requires a
source-only bounded startup-error classification design, independent
review, and a separately authorized exact native diagnostic. Production
remains HOLD.
