# EA-4E.92IU first inert gateway smoke denied

Status: DENIED AT CONTAINER-INSPECT POLICY GATE / EXACT CONTAINER REMOVED.
Governing source commit: `0602b52843a88f768f7a0a28172fdec0ecf19daf`.
Image index: `sha256:afdd2f974bb91d8b3c9bc8da6dd2ac4c2667d4fe1c4e756b0e818e9eff5cd511`.

The operator approved one inert gateway-container smoke. The command created
and started one temporary container with `--network none`, `--read-only`,
`--cap-drop ALL`, `--security-opt no-new-privileges`, a PID/memory/CPU limit,
no mount and no published port. The only added environment values were the
fake-only marker, synthetic attempt/task/receipt identities, and a synthetic
task-bound SSE response with its SHA-256. No Kilo or OpenCode receiver, model,
GPU, ComfyUI or production activation was invoked.

Created container ID:
`cad6f1b02b3de192f113980280fa5de110039b6f1ad70a50f31b976ea5d1fa93`.
The immediate Docker inspect returned, but the combined policy predicate
rejected before printing individual fields or reaching the 20-second idle
behavior check. The `finally` block removed that exact ID. A subsequent
read-only `docker ps -a` by exact ID and candidate-image ancestry returned
no containers. The sole approved run was consumed; there was no automatic
retry or signal-based release.

Read-only image inspection after cleanup confirmed an OCI image-index
descriptor at the pinned digest. A comparison of the pinned index with a
container's image-config identity is a plausible cause, but the removed
container's field values were not retained, so the exact failed predicate
is **unproven**. A new attempt must print and check each inspect field
individually before start, bind the index/config pair explicitly, and require
separate one-run authorization. This failure is not a pass for gateway
startup, idle timeout, request handling, Docker peer attribution, receiver
integration, or production readiness. Strict 92AT proof remains HOLD.
