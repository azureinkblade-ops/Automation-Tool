# EA-4E.92EQ Synthetic Gateway Peer Binding

Status: FAKE-ONLY QUALIFIED / PRODUCTION HOLD
Baseline before this change: `fb93108b09bbdfa52d050db99c7ce3feb9c7a317`
Date: 2026-10-07 (America/Phoenix)

This checkpoint connects the 92DW dynamic-body fake gateway's injected peer
seam to the existing 92DY candidate comparator using synthetic socket-peer and
daemon-snapshot records. The verifier binds the fake scope's exact network and
receiver IDs plus an explicitly supplied gateway ID. It rejects wrong socket
addresses, extra network members, missing snapshots, and untyped contexts.
The gateway invokes the injected snapshot reader before the claim and again
inside the store's precommit validation. A changed second snapshot denies
the request without consuming the budget or calling the fake responder.

This is **not** a real Docker verifier. `SyntheticAcceptedPeer` does not prove
which process supplied an address, and the injected reader does not establish
freshness, daemon identity, or a real accepted socket. The new module imports
no Docker CLI, subprocess, socket, network, receiver, or model capability.
The existing exact-hash gateway and production routes are unchanged.

Focused fake-only qualification: 115 passed, 1 existing gated skip, 0 failed
across dynamic and exact-hash gateways, request shapes, peer comparator, inert
observation, and probe coordinator/driver tests. One test expectation was
corrected to account for the durable store wrapping a precommit peer denial.
No Docker object was created; no Kilo/OpenCode/model request was made.

Next: design a real accepted-socket context owner and a fresh per-attempt
daemon-snapshot provider, then fake-test the combined request lifecycle and
teardown. Separately qualify the Linux Kilo image/input/effective-container
binding before asking for a new bounded receiver probe. The 92AT exact-byte
route remains REJECT; the 92DE local provenance claim remains unearned.

`SYNTHETIC_GATEWAY_PEER_BINDING=PASS_FAKE_ONLY`
`REAL_SOCKET_PEER_OWNER=NO`
`FRESH_DAEMON_OBSERVATION=NO`
`PRODUCTION_PEER_VERIFIER_QUALIFIED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`PRODUCTION_READY=NO`
