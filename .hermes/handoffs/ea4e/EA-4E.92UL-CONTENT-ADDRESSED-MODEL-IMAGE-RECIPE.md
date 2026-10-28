# EA-4E.92UL content-addressed model-image recipe

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / NATIVE HOLD / PRODUCTION HOLD

The 92UK independent review held the 92UJ bind-mount candidate for any
exact model-byte pinning claim: host files can change during the mounted
interval. This checkpoint adds a minimal Dockerfile derived from the pinned
Ollama base image. It copies only the six reviewed qwen3:14b paths into
`/models` and contains no `RUN`, network, entrypoint, or model invocation.

Focused strict source/fake tests passed (115/115) across the recipe, shared
container smoke runner, and adjacent Bash transport checks. No Docker build,
container, Ollama server, inference, GPU, receiver, or agent handoff occurred.

This recipe alone does not establish immutable model bytes. The mutable host
build context could change between preflight and Docker's copy; a build may
also consume substantial storage and could contact a registry if the local
base is missing. Before any native build, independently review a bounded,
offline, minimal-context build launcher with explicit disk/time/output limits
and failure reconciliation. After build, verify the resulting image's exact
six-file inventory and SHA-256 values from the image, not just from the host,
then pin its content-addressed image ID. Only that verified image may become
a candidate for a separate non-model startup check and later model smoke.
No direct build or model use is authorized by this checkpoint.

Docker documentation describes image layers as immutable and image IDs as
content-addressed. References:
- https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-an-image/
- https://docs.docker.com/reference/cli/docker/image/pull/
- https://docs.docker.com/build/concepts/context/

Production remains HOLD.
