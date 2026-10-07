# EA-4E.92EJ one-shot inert peer probe result

Status: HOLD AT PRESTART METADATA / ONE-SHOT APPROVAL CONSUMED
Governing commit: `748f8f1a29047be959a074a1465fb186090dde4f`
Date: 2026-10-07 (America/Phoenix)
Run ID: `e2444e79d4a04bf88d44dfec9d2fdf55`
Pinned image ID:
`sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`

The operator explicitly approved one bounded v2 inert Docker peer probe
using the pinned image, one fresh internal network, two temporary helpers,
one release signal only after a matching live observation, and exact-object
cleanup. Preflight rechecked the image ID and the committed tree; the
coordinator and mocked driver had passed 87/87 focused tests.

The one invocation created the scoped network and two containers, then
stopped in `inspect_inert_peer_created()` with
`InertPeerCreatedDenied: container network binding denied`. That check
requires an exact single network attachment and the created-container
`NetworkID` equal to the returned network ID. The current driver did not
persist a sanitized copy of the failed inspect fields, so the precise
subfield mismatch is **unknown**. No check was relaxed and there was no
retry. The failure occurred before either `start_container()` call, before
the gateway could accept a socket, and before any `SIGUSR2` release.

The coordinator's failure record reported no remaining owned network or
container IDs. Independent read-only `docker network ls` and
`docker container ls --all` checks filtered by the exact run label returned
no objects. No Kilo/OpenCode receiver, credential, model, GPU, ComfyUI,
provider call, or production activation was involved.

The one-shot approval is consumed. A next non-live remediation should make
the prestart denial report only bounded, sanitized network-binding fields
while still cleaning up exact owned IDs. A later diagnostic-only create and
inspect probe needs its own exact authorization; do not rerun this one or
infer the missing Docker field from the generic exception. The 92DX live
peer-binding claim remains unqualified, and the strict 92AT mapped-byte
route remains rejected separately.

`ONE_SHOT_PROBE_EXECUTED=YES`
`ONE_SHOT_APPROVAL_CONSUMED=YES`
`PRESTART_METADATA_MATCH=NO`
`CONTAINERS_STARTED=0`
`RELEASE_SIGNALS_SENT=0`
`MARKER_REQUESTS=0`
`LEFTOVER_LABELED_OBJECTS=0`
`PEER_QUALIFIED=NO`
`PRODUCTION_READY=NO`
