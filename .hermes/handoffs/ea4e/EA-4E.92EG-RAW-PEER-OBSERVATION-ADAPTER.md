# EA-4E.92EG raw peer-observation adapter

Status: PURE/FAKE ADAPTER PASS / LIVE PEER PROOF HOLD
Baseline: `1898bcfcfbce860c946151bd3f163bc0131c0bd7`
Date: 2026-10-07 (America/Phoenix)

`tools/hermes_core/inert_peer_observation.py` maps supplied Docker-shaped
network and container inspect records plus the held-open helper's
`PEER_ACCEPTED` event into the existing 92DY candidate comparator. It
requires the canonical v2 plan, exact two-member internal bridge, one
network attachment per running container, consistent network/member and
container endpoint IPv4 addresses, no published ports or mounts, and the
accepted socket peer equal to the client endpoint. It rejects extra event
fields rather than treating forwarded metadata as socket identity.

The new tests and 92EC/92EB/92EA/92DY adjacent fake-only tests passed
78/78. The adapter imports no subprocess, Docker client, socket, or
network service. Its positive output remains
`RAW_OBSERVATION_CANDIDATE_ONLY`, `peer_qualified: false`, and
`release_authorized: false`.

All records in the tests are synthetic. This adapter cannot attest that
the daemon snapshot was fresh, simultaneous with the pending request, or
collected from the exact created object IDs. It does not signal a gateway,
start a container, or clean up. A separately qualified coordinator must
establish those timing, one-shot, and cleanup facts before an explicitly
authorized inert probe can yield real peer evidence. The strict 92AT
mapped-byte requirement remains rejected on its separate route, and the
local Docker profile is not production ready.

`RAW_OBSERVATION_ADAPTER=FAKE_PASS`
`FOCUSED_TESTS=78_PASS`
`DOCKER_CALLS=0`
`RELEASE_AUTHORIZED=NO`
`PEER_QUALIFIED=NO`
`PRODUCTION_READY=NO`
