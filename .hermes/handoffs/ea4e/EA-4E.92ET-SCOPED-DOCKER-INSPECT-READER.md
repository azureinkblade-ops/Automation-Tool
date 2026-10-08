# EA-4E.92ET Scoped Docker Inspect Reader

Status: FAKE-COMMAND QUALIFIED / RUNTIME BINDING HOLD
Baseline before this change: `9d224a58ab33d9a0c01f6adfda92a2d317161d36`
Date: 2026-10-07 (America/Phoenix)

The new reader accepts only three distinct lowercase 64-hex IDs: a network,
receiver container, and gateway container. Each `read()` issues only
`docker network inspect <network-id>` and `docker container inspect` for the
two bound container IDs. It parses one JSON object per command, requires the
returned IDs to equal the bound IDs, limits output size, sets a 10-second
command timeout, and fails closed on malformed or unsuccessful output. It
returns a raw snapshot for the 92ER fake comparator; it does not create,
start, signal, remove, or invoke a container or model.

Qualification used an injected fake command runner. The broader fake-only
gate passed 144 tests with one existing gated skip and zero failures. No
Docker command was issued by those tests, and no real Kilo/OpenCode receiver,
provider, GPU, ComfyUI, or production path ran.

The default command still resolves `docker` through PATH; its executable
identity is not pinned. The three daemon reads are sequential, not an atomic
snapshot, and no real accepted-socket owner supplies the peer address. The
reader has not been bound to the gateway's request lifecycle, and the Linux
Kilo image/mount/effective launch remains unqualified. This checkpoint does
not establish fresh authoritative daemon observation or production peer
verification. Any real read/probe requires a separate bounded review.

`SCOPED_INSPECT_COMMAND_SHAPE=PASS_FAKE_ONLY`
`DOCKER_EXECUTABLE_PINNED=NO`
`ATOMIC_DAEMON_SNAPSHOT=NO`
`REAL_SOCKET_OWNER=NO`
`PRODUCTION_PEER_VERIFIER_QUALIFIED=NO`
`PRODUCTION_READY=NO`
