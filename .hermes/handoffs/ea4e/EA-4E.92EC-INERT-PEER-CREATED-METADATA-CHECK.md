# EA-4E.92EC inert peer created-metadata check

Status: FAKE-ONLY PRESTART CHECK PASS / DOCKER PEER PROBE HOLD
Baseline: `f2aeab3fe6a4078f971169bcccfa89c1530ed97f`
Date: 2026-10-07 (America/Phoenix)

`tools/hermes_core/inert_peer_created_check.py` is a pure comparator for
the canonical 92EA plan, pinned helper image, and synthetic `docker inspect`
records for a created internal network and exactly two created containers.
It denies wrong network identity or driver, external network, foreign
membership, already-running containers, wrong image/config/command, added
environment, published ports, mounts, privilege, device requests, extra
hosts, or a missing gateway alias. It imports no subprocess, Docker client,
socket, or network library. Its positive result explicitly says
`start_authorized: false` and `peer_qualified: false`.

The new checker and adjacent preflight/plan/peer-candidate tests passed
61/61. An initial fake `extra-env` test exposed shared-list aliasing in the
test fixture. The fixture was corrected to use independent copies, and the
full focused gate then passed. Production logic was not weakened to make
the test pass.

These are synthetic inspect records only. No network or container was
created or started, and no actual Docker-created metadata was compared.
The checker may deny a future real Docker record if the daemon represents
a field differently; such a denial is a HOLD requiring review, not an
invitation to bypass the check. Even a real metadata match would not
establish socket peer identity, helper image reproducibility, or the
strict 92AT mapped-byte invariant. The separately governed one-shot inert
peer probe remains pending.

`FAKE_PRESTART_CHECK=PASS`
`FOCUSED_TESTS=61_PASS`
`START_AUTHORIZED=NO`
`PEER_QUALIFIED=NO`
`DOCKER_OBJECTS_CREATED=0`
`KILO_RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
