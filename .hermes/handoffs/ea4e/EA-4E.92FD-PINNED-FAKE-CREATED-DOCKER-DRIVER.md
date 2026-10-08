# EA-4E.92FD Pinned Fake Created Docker Driver

Status: FAKE-CLI QUALIFIED / READ-ONLY REAL PREFLIGHT PASS / CREATE HOLD
Baseline before this change: `2f6c1857d91b5ebb31f299c1f244ba3aecc1c8b6`
Date: 2026-10-08 (America/Phoenix)

The diagnostic-only driver requires an absolute nonsymlink Docker executable
whose SHA-256 is rechecked before each command. Create argv must equal the
canonical 92EZ plan. It has image/name inspect, create, exact-ID inspect, and
owned-object cleanup methods, but no start, signal, request, receiver, or
model method. On a lost create response, cleanup re-inspects only the three
run-scoped names, checks exact name/run label/image and non-running state,
removes by exact returned ID, then checks label-filtered leftovers. A mismatch
is a terminal denial and is not removed as though owned.

12 focused fake-CLI driver/coordinator tests passed. A separate read-only
preflight using the installed Docker executable at
`C:\Program Files\Docker\Docker\resources\bin\docker.exe`, SHA-256
`c11b843b727ea76e6c63b393bccb73d957b6fcc12ba871c8265699e3a12e933c`,
matched both cached images and the current name inventory. That observed CLI
hash is a one-run pin, not enduring production authority. No network or
container was created or started by this checkpoint.

Next: rerun the focused committed-tree gate, then a separately bounded
never-started diagnostic can determine whether real Docker created records
match the 92FB gate. Any denial stops before start and must record exact-ID
cleanup. Even a match would not qualify a live socket peer or production.

`PINNED_DRIVER_FAKE_TESTS=PASS`
`REAL_DOCKER_PREFLIGHT=PASS_READ_ONLY`
`DOCKER_OBJECTS_CREATED=NO`
`CONTAINERS_STARTED=NO`
`PRODUCTION_READY=NO`
