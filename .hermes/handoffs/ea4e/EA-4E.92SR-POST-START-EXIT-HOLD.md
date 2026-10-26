# EA-4E.92SR post-start exit HOLD

Date: 2026-10-26

The user authorized exactly one tags-only native diagnostic at source
commit `b561c7e66549ea19e150336132e28943e8d240b7`. Fresh preflight
confirmed the authorized entrypoint, runner, and Docker CLI SHA-256 values;
the six pinned `qwen3:14b` files and empty `manifests-v2` directory; and
absence of an old `ea4e92rm-` container.

The one invocation passed its first effective-container inspection and
attempted container start. The next inspection failed only the fixed
`running` predicate: the container was not running. The launcher stopped
before interface inspection or `/api/tags`. It made no generate request,
inference, receiver call, agent handoff, GPU assignment, or production
activation. Exact-owned cleanup completed; a separate read-only Docker
query found no remaining `ea4e92rm-` container. The one-shot approval is
consumed, with no retry.

The process exit reason is unknown. Logging was disabled by the containment
contract, and the container was removed, so there is no observed exit code
or server diagnostic in this checkpoint. Do not infer that the empty v2 root
fixed or caused the prior `/api/tags` read-only-filesystem error. Next is a
source-only design for a bounded, non-sensitive post-start exit classifier,
independent review, and a separately authorized exact native attempt. Do
not relax the containment envelope on speculation. Production remains
HOLD.
