# EA-4E.92ES Raw Peer Fake Gateway Recheck

Status: FAKE-ONLY QUALIFIED / PRODUCTION HOLD
Baseline before this change: `904649b58e7a1728f1145d7642fcc4abd857a227`
Date: 2026-10-07 (America/Phoenix)

The 92ER raw-record candidate is now usable as an injected peer verifier in
the 92DW dynamic-body fake gateway. On each validation it requests a supplied
Docker-shaped snapshot and compares exact per-attempt network, receiver, and
gateway identities plus the synthetic accepted peer. The gateway calls the
reader once during request validation and again inside the durable store's
precommit validation. A changed second-read member set denies before claim;
the budget remains unconsumed and no fake response is sent.

This does not prove the injected reader returns fresh daemon observations, or
that `SyntheticAcceptedPeer` came from a real accepted socket. It does not
establish container image/mount provenance, cancellation durability, or
teardown ownership. No Docker CLI, receiver, model, GPU, ComfyUI, or live
provider path was invoked or enabled.

Focused fake-only gate: 133 passed, 1 existing gated skip, 0 failed across
the raw comparator, dynamic/exact-hash gateways, body schemas, peer candidate,
inert observation, coordinator, and driver. The strict 92AT mapped-byte path
remains REJECT; the 92DE local provenance claim remains unearned.

`RAW_PEER_FAKE_GATEWAY_RECHECK=PASS_FAKE_ONLY`
`FRESH_DAEMON_READER=NO`
`REAL_ACCEPTED_SOCKET_OWNER=NO`
`PRODUCTION_PEER_VERIFIER_QUALIFIED=NO`
`PRODUCTION_READY=NO`
