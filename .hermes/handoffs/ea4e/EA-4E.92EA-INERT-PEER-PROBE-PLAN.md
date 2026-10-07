# EA-4E.92EA inert peer-probe command plan

Status: PURE PLAN PASS / DOCKER PROBE NOT AUTHORIZED
Baseline: `67804eabbe2ad8c3f16d839ae0bcbc9263f03e9f`
Date: 2026-10-07 (America/Phoenix)

`tools/hermes_core/inert_peer_probe_plan.py` returns Docker argv as data
only. It has no subprocess, Docker API, socket, network, or receiver
capability. A 32-character lowercase-hex run ID creates unique full-length
network and container names. The plan pins exact provisional helper image ID
`sha256:de6495938a8fb3fb1745f1d955d0b56b0d3dd3283bd8f6e20c7ad020d31c72f9`;
no mutable tag is used in the container-create argv.

The proposed internal bridge has a per-run label. The two proposed
containers use the pinned helper image with `--pull never` and explicit
Linux/amd64, user `node`, read-only root, all
capabilities dropped, no-new-privileges, bounded CPU/memory/pids, no
published ports or mounts, and fixed `gateway`/`client` modes. The gateway
has network alias `ea4e-peer-gateway`, matching the client's fixed
destination. Review caught and corrected that alias requirement before any
Docker action. Planned observations include the daemon-reported image,
network ID and membership, both container IDs/states, no published ports or
mounts, the gateway's socket peer, marker/exit, and post-exit membership.
Cleanup is limited to exact IDs returned by creation. The plan has no
execution or cleanup function, and `probe_authorized` is false.

The new pure tests plus adjacent fake-peer/gateway tests passed 46/46. This
does not establish Docker Desktop's actual network behavior. The local image
ID changed across two builds despite identical source hashes; 92DZ records
that limitation. The specific image ID in this plan must be re-inspected
before a separately approved one-shot probe. The pending approval question
is not authorization until the user answers it explicitly. No container or
network was created in this phase.

`PURE_PROBE_PLAN=PASS`
`CURRENT_IMAGE_ID_CANDIDATE=de6495938a8fb3fb1745f1d955d0b56b0d3dd3283bd8f6e20c7ad020d31c72f9`
`DOCKER_PEER_OBSERVED=NO`
`PEER_PROBE_AUTHORIZED=NO`
`KILO_RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
