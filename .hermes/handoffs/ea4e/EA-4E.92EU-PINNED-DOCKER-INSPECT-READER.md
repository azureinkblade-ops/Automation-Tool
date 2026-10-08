# EA-4E.92EU Pinned Docker Inspect Reader

Status: FAKE-COMMAND QUALIFIED / RUNTIME BINDING HOLD
Baseline before this change: `9de3aa18fcb00cbbc5ae103989e5dd91fe599028`
Date: 2026-10-07 (America/Phoenix)

92ET's PATH-based Docker executable resolution has been removed. The scoped
reader now requires an absolute executable path and lowercase SHA-256 digest,
rejects a symlink or missing file, hashes the file before each three-inspect
read, and denies a changed digest before invoking its command runner. Its
command shape remains limited to one exact network ID and two exact container
IDs. Tests use an inert temporary file and fake command runner; no Docker
daemon or receiver is contacted by the test suite.

The wider fake-only ladder passed 145 tests with one existing gated skip and
zero failures. A separate read-only host inventory observed the current CLI
at `C:\Program Files\Docker\Docker\resources\bin\docker.exe` with SHA-256
`c11b843b727ea76e6c63b393bccb73d957b6fcc12ba871c8265699e3a12e933c`.
That observation is not a durable runtime binding and may change with Docker
updates; no production authorization uses it.

The three daemon reads remain sequential rather than atomic. A real accepted
socket owner, request-scoped reader binding, Linux Kilo image/input/effective
container admission, and teardown/recovery evidence remain open. No real
Kilo/OpenCode/model, GPU, ComfyUI, or production activation occurred.

`PINNED_CLI_POLICY=PASS_FAKE_ONLY`
`CURRENT_CLI_HASH_OBSERVED_READ_ONLY=YES`
`RUNTIME_DOCKER_READER_BOUND=NO`
`REAL_SOCKET_OWNER=NO`
`PRODUCTION_PEER_VERIFIER_QUALIFIED=NO`
`PRODUCTION_READY=NO`
