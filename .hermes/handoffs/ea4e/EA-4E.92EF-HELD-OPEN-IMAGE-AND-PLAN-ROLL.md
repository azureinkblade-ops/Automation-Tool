# EA-4E.92EF held-open helper image and probe-plan roll

Status: PROVISIONAL IMAGE + PURE PLAN PASS / LIVE PEER PROBE HOLD
Baseline: `72e76b284b0fc5a49e60abbddd77981437f4db57`
Date: 2026-10-07 (America/Phoenix)

The committed 92EE source was built as a new provisional Linux/amd64
helper image from cached pinned base
`sha256:3144a862c5947599f5eeab3f9dfde33a690fa98d01065b9d66576da43a692561`.
The build used `--pull=false --network=none`; its Dockerfile has no `RUN`
step. This does not independently prove zero builder metadata network
requests or image reproducibility. No container was created or started.

New image ID:
`sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`.
Read-only image inspection returned Linux/amd64, user `node`, workdir
`/opt/ea4e-peer`, and entrypoint
`["node", "/opt/ea4e-peer/marker.js"]`. The mutable local tag is not a
probe authority. Committed source SHA-256 values:

- Dockerfile: `81f5f955fc73cf8b9e95abf6bb147a22c23b34ff1c3b909ebc6174d3c70f9f8a`
- marker.js: `6c945023a1ca78e3cd40f11dcd056114903f7b58464a1679bea6ec3705648817`

The pure probe-plan schema was rolled to v2. It pins the new image ID,
requires the gateway's request to remain pending during a fresh
running-state daemon inspection, and records `SIGUSR2` as the release
signal to the exact created gateway ID only after peer/membership match.
The total planned timeout is 45 seconds. The plan still returns
`probe_authorized: false`, and its returned argv is data only. The 92EA,
92EB, 92EC, and 92DY pure/fake-only tests passed 61/61 after the roll;
the 92EE and original helper source-only Node tests passed 6/6 before the
image build.

The host-side coordinator that observes the pending peer, performs the
fresh running-state inspection, enforces one release signal, and records
cleanup does not exist yet. No real socket-peer observation was made. The
new image is not proven reproducible. The old 92EA v1 image/plan and its
pending one-shot approval are not valid for this v2 protocol. A new exact
one-shot authorization is required after the coordinator and fake-only
failure tests qualify. No Kilo receiver, model, or production activation
was invoked.

`PROVISIONAL_IMAGE_BUILT=YES`
`PURE_PLAN_ROLLED=YES`
`FAKE_TESTS=61_PASS`
`NODE_TESTS=6_PASS`
`REPRODUCIBLE_IMAGE_ID=NO`
`HOST_COORDINATOR_QUALIFIED=NO`
`PEER_PROBE_AUTHORIZED=NO`
`CONTAINERS_STARTED=0`
`PRODUCTION_READY=NO`
