# EA-4E.92ER Raw Kilo Peer Candidate

Status: FAKE-ONLY QUALIFIED / PRODUCTION HOLD
Baseline before this change: `01f1e1156a1f4dc462cee24aedd66d217b82ce86`
Date: 2026-10-07 (America/Phoenix)

This checkpoint adds a pure comparator for Docker-shaped network and
container inspect records under the accepted local-Docker threat model. It
requires exact scoped network and receiver IDs, an explicitly bound gateway
ID and network name, internal bridge with IPv6 disabled, exactly two members,
matching running endpoints and IPv4 member addresses, one attachment per
container, and no published ports. The supplied synthetic socket peer must
equal the receiver member IP. Wrong/extra members, host mode, changed IP,
empty running endpoint ID, IPv6 endpoint, stopped peer, and header-like or
untyped peer contexts are denied.

The comparator does not call Docker, open a socket, launch a receiver, or
inspect image/mount provenance. Its input records can be fabricated by the
test caller. It returns `FAKE_RAW_PEER_MATCH_ONLY` with
`peer_qualified=false`, never an execution or release authorization.

Focused fake-only ladder: 131 passed, 1 existing gated skip, 0 failed across
the raw candidate, synthetic gateway seam, body shapes, peer comparator,
inert observation, coordinator, and driver tests. No Docker object, Kilo
process, model call, or production activation occurred.

Next non-live work must bind a real accepted-socket owner and fresh
request-scoped Docker daemon reads to this comparison, with replay, drift,
failure, and cleanup tests. Separately bind the Linux Kilo image/index,
prepared inputs, and effective launch configuration. The 92AT strict
mapped-byte route remains REJECT; the 92DE local provenance claim is not yet
qualified.

`RAW_KILO_PEER_CANDIDATE=PASS_FAKE_ONLY`
`REAL_SOCKET_OWNER=NO`
`FRESH_DAEMON_READER=NO`
`IMAGE_AND_MOUNT_PROVENANCE=NO`
`PRODUCTION_PEER_VERIFIER_QUALIFIED=NO`
`PRODUCTION_READY=NO`
