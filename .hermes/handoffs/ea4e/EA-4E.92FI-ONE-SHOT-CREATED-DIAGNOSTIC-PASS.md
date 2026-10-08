# EA-4E.92FI One-Shot Created Diagnostic

Status: PASS FOR NEVER-STARTED CREATED STATE ONLY
Governing source commit: `38a4e45549287f13edf407acaaddcfd0d9a68c63`
Date: 2026-10-08 (America/Phoenix)
Run ID: `77329ef1b7554732843daddccc7371ba`

The tracked worktree was clean and local/remote were synchronized at the
governing commit. The installed Docker CLI SHA-256 matched its pinned value,
`c11b843b727ea76e6c63b393bccb73d957b6fcc12ba871c8265699e3a12e933c`.
The read-only two-image/name preflight returned `FAKE_IMAGE_PREFLIGHT_ONLY`.

Exactly one bounded diagnostic created one internal network and two inert,
never-started containers. The exact-ID created-state checker returned
`FAKE_CREATED_DIAGNOSTIC_ONLY` with these owned IDs:

- Network: `ff4c0f587fecc987f22daa2b27533a7f03387fae948f71a0dc89c172943ebe03`
- Gateway: `064a22161f0d7568e1827a181afe56cd5b4e4e837dd5a21092c4546057321861`
- Client: `ba18f0ef14b925f850a183b64fc4e9e214eed05d701d550a9fb6fef56fb3ad95`

The coordinator completed exact-ID cleanup. A separate read-only Docker
container and network listing filtered by the actual
`hermes.ea4e.run=77329ef1b7554732843daddccc7371ba` label returned no
objects. An initial independent check used the wrong label key and was
repeated with the contract's actual key; only the latter is cleanup evidence.

This proves the current image/name/created-state contract for this one run.
It does not identify the historical 92FE denial subfield and does not prove
running peer binding, request delivery, release control, Kilo/OpenCode
execution, or production readiness. A separately bounded inert running
request probe is the next gate; it is not authorized by this result.

`CREATED_STATE_MATCH=YES`
`CONTAINERS_STARTED=0`
`REQUESTS_SENT=0`
`RELEASE_SIGNALS_SENT=0`
`LEFTOVER_RUN_SCOPED_OBJECTS=0`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
