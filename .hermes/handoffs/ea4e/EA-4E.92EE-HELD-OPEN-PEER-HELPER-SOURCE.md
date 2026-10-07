# EA-4E.92EE held-open peer helper source

Status: SOURCE-ONLY HELPER CANDIDATE / NO IMAGE OR DOCKER PROBE
Baseline: `192a6353c707cacfbfc32a96ac2a472705f234f9`
Date: 2026-10-07 (America/Phoenix)

The new `ea4e92ee_peer_probe` helper leaves the one fixed `GET /marker`
request pending after recording the accepted socket remote address. It
returns the constant marker only after a `SIGUSR2` release received while
that request is pending. An early signal does nothing. Timeout, invalid
request, or a disconnected client cannot subsequently be released; the
gateway records a nonzero terminal status. The client has a bounded wait.
No prompt, credential, Kilo command, provider route, or model call was
added. The old 92DZ helper was not modified.

The new and original helper unit tests passed 6/6 through the local Node
runtime. Those tests use synthetic request/response objects; they do not
open a service, build an image, create a network, or start a container.

This source alone does not close 92ED. A future bounded coordinator must
observe `PEER_ACCEPTED`, read fresh daemon records while both containers
are running and the request is still pending, compare the accepted peer
to the exact receiver endpoint and sole network membership, and only then
send one reviewed release signal to the exact gateway container ID. A
timeout or any mismatch must leave the marker unreleased and fail closed.
The release signal is an additional Docker action requiring explicit
scope in a new one-shot authorization. The source must first be packaged
under a new immutable image identity, and the pinned plan and fake
metadata checks must be rolled and requalified. The old 92EA image ID and
pending approval do not transfer to this helper.

`HELD_OPEN_HELPER_SOURCE=PASS`
`SOURCE_ONLY_NODE_TESTS=6_PASS`
`NEW_IMAGE_BUILT=NO`
`OLD_PROBE_PLAN_VALID_FOR_NEW_HELPER=NO`
`DOCKER_OBJECTS_CREATED=0`
`PEER_QUALIFIED=NO`
`PRODUCTION_READY=NO`
