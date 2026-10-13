# EA-4E.92IX fake request/peer probe result

Status: PASS for synthetic request ingestion, pending-event lineage, and
daemon-observed internal-network membership only.
Governing HEAD: `f11d237a5527c2200284fb17e4ae21f0d178c3fc`.
The operator separately approved one 92IW fake pair probe. This approval
was consumed by the single run below; there was no retry or release signal.

Pinned images:

- Versioned gateway index:
  `sha256:afdd2f974bb91d8b3c9bc8da6dd2ac4c2667d4fe1c4e756b0e818e9eff5cd511`.
- Dummy Node client:
  `sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`.

The probe created one fresh labeled, internal-only bridge network and two
fresh labeled containers, all by exact ID. Before start, both containers
matched their pinned image indices, network name, read-only root, zero
mounts and port bindings, dropped capabilities, no-new-privileges and
`Running=False`. The network was internal and used the bridge driver.
No host port, credential, provider configuration, receiver binary, model,
GPU/ComfyUI or production activation was used.

The gateway started once, followed by the dummy client. The client sent
one bounded POST with the 92IS `ea4e-inert` seven-field streaming shape.
The gateway emitted one `FAKE_PING_REQUEST_PENDING` event with the expected
synthetic attempt and response digest. Its request evidence was:

```ini
body_bytes=205
body_sha256=05bdede8d5f9b10a2a2e921ee427df3567f796ed0f22355893a6171c4d9de789
reported_peer_ip=172.19.0.3
daemon_client_ip=172.19.0.3
daemon_gateway_ip=172.19.0.2
```

Fresh daemon inspection placed both containers on the created network
with the matching network ID while both were running. The event's peer
address matched the dummy client's daemon-observed IP. This is a network
membership comparison under the accepted local-container threat model;
it is **not** independent socket-owner attestation. The client had no log
line before cleanup. No SIGUSR2 release occurred, so no successful SSE
response or result return was observed.

The command removed the exact client ID, gateway ID and network ID.
Follow-up read-only queries by those IDs returned no objects. Their full
IDs are recorded below for cleanup attribution:

```ini
network_id=71cb8a87ee1ec7c3f6234362c83661b3f04ef3766f19c2925ec7ceaecd632ef2
gateway_id=91fe9a40292cfc4bfb6e2d41b2ed1a30e0374c0b8bd8bb95ab8c5592f666637c
client_id=0ecbd16abc28aaaa64d247ff52d2998527e34adef14f5e23d21596c354ce3572
```

Remaining gates: trusted request-scoped release ownership, one-use
response delivery, real Kilo SDK body compatibility and receiver result
lineage, OpenCode, cancellation/recovery, and explicit activation. A
separately authorized fake release probe should precede any real receiver
call. The original strict 92AT mapped-byte requirement remains HOLD and
is not satisfied by this local-container evidence. Production readiness
remains HOLD.
