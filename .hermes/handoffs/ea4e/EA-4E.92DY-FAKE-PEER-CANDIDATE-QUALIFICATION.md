# EA-4E.92DY fake Docker peer-candidate qualification

Status: PURE FAKE-ONLY PASS / REAL DOCKER PEER HOLD
Baseline: `e64a49428195d51b07933b836f5028a4fc8282c9`
Date: 2026-10-07 (America/Phoenix)

The 92DX source-only contract now has a pure comparator in
`tools/hermes_core/docker_peer_candidate.py`. It accepts normalized synthetic
network/container snapshots and an observed socket-peer address supplied by
the test. It makes no Docker API, network, process, credential, or model call.
Its only positive result is `CANDIDATE_MATCH_ONLY`, with
`peer_qualified: false`; it is not wired into the gateway or production app.

The candidate denies a wrong/stale network ID, non-bridge or non-internal
network, missing/extra member, duplicate endpoint address, stopped or
substituted container, multi-homing, published ports, host/gateway-origin
socket address, and ambiguous IPv6-mapped representation. The comparison
requires exact receiver/gateway IDs and one network ID. Tests exercise those
denials and verify no Docker/socket/subprocess imports. The focused
candidate plus existing fake gateway/shape/exact-hash tests passed 70/70.

This is deliberately not runtime peer proof. A future adapter must obtain
the socket address from the accepted connection and fresh membership/state
from the trusted daemon, prove those observations are from the same attempt
and close enough to the durable claim, and test actual Docker Desktop
behavior in a separately authorized inert probe. A caller-supplied snapshot
or HTTP header is never sufficient. The local-profile trust boundary and
strict 92AT mapped-byte REJECT/HOLD are unchanged.

`FAKE_PEER_CANDIDATE=PASS`
`DOCKER_DAEMON_OBSERVED=NO`
`PRODUCTION_PEER_VERIFIER=UNQUALIFIED`
`LINUX_KILO_RECEIVER_EXECUTED=NO`
`REAL_UPSTREAM_SEND_AUTHORIZED=NO`
`PRODUCTION_READY=NO`
