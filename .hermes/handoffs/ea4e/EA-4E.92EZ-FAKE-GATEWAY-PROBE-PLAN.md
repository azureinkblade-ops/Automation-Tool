# EA-4E.92EZ Fake Gateway Probe Plan

Status: SOURCE-ONLY PLAN PASS / RUNTIME PROBE HOLD
Baseline before this change: `3a445bfa4b572dc17eb2dbf1e383d08c77677d45`
Date: 2026-10-08 (America/Phoenix)

The pure plan freezes one private-network exchange between the offline-built
92EX fake gateway and the pre-existing inert Node helper image. The gateway
is referenced by its local index digest
`sha256:ba59552b483c3fb3a13880da33197f29cada670b80c38862eaa587bed84c3787`;
read-only platform selection resolves to Linux/amd64 manifest
`sha256:7d812fc364c8f4dd47e6b25f83d4074c212fa5ad348d4cda9251b8734557420b`.
The inert client image index is
`sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`.
Both references resolved locally without a pull.

The plan has one internal bridge network, two read-only/non-root containers,
no mounts or published ports, `--pull never`, and a fixed tiny POST. It records
the expected body digest and length; the client expects only the fixed inert
SSE response. The client script passed `node --check` without execution. The
new plan/event tests passed 24/24. `probe_authorized` remains false: this file
does not create or start Docker objects and does not grant a signal, receiver,
model, or production call.

Before any runtime probe, a coordinator must verify exact created IDs,
image/config identity, private network and two-member set, no published ports
or mounts, one bounded pending event matching the expected body digest/length,
fresh running peer observation before one release, exits, and exact-ID cleanup.
This would qualify only the inert fake exchange, not Kilo/OpenCode.

`PLAN_SOURCE_ONLY=PASS`
`IMAGE_REFERENCES_RESOLVE=YES_READ_ONLY`
`PROBE_EXECUTED=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
