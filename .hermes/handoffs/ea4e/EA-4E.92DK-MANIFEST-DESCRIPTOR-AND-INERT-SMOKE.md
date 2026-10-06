# EA-4E.92DK manifest descriptor and inert container smoke

Status: NON-LIVE INERT SMOKE PASS / RECEIVER LAUNCH HOLD
Baseline: `0c43fd607d44dec6b37f5629a26337f9147d2019`
Date: 2026-10-06 (America/Phoenix)

The operator separately approved one inert Docker smoke with an overridden
`/bin/true` entrypoint, no network or mounts, no Kilo/model call, and removal
of the temporary container afterward. This approval did not cover receiver
launch, model invocation, production activation, or a second smoke.

The pure image-admission checker now additionally requires the inspected
Linux/amd64 OCI manifest descriptor: digest
`sha256:2eaab2a5675726461630106859873c29f03641c142ae47c6b6060aebc611504d`,
media type `application/vnd.oci.image.manifest.v1+json`, and platform
`linux/amd64`. Missing/mismatched descriptors deny. Five new fake-only cases
cover descriptor denial. Focused image-admission, Kilo adapter/binding,
production wiring, and app-host tests: 199 passed, 0 failed. Read-only
`docker image inspect --platform linux/amd64` returned `MATCH`; the checker
still reported both execution and provenance false.

One container was created as `ea4e92dk-inert-20261006`, ID
`9aa46f6e6453daa654a1f20325bca37675ffdb8d57853c2fa2dca299a50df0a3`.
Before start, daemon inspection reported `created`, `/bin/true` entrypoint,
no command, UID:GID 65532:65532, `network=none`, read-only root, no mounts,
all capabilities dropped, no-new-privileges, pids limit 32, memory 64 MiB,
and 0.25 CPU. The container's `.Image` field was the local index digest
`sha256:c170379623cd8d16feb2c15fcdd473c401275336dc046fe72a5a5075c3474303`,
not the platform manifest digest. A future checker must bind the observed
index to the independently inspected exact-platform manifest rather than
compare those different fields as if they were interchangeable.

The container was started once. `docker wait` returned 0. Post-run inspection
reported `exited`, exit code 0, `OOMKilled=false`, no daemon error, no mounts,
`network=none`, and `/bin/true`. The approved temporary container was then
removed by exact name; a filtered `docker ps --all` returned no match. No
other containers or image files were removed.

This proves only the bounded inert create/inspect/start/wait/remove path.
It does not test a writable runtime home, receiver config, credentials,
network egress, Kilo execution, model output, durable attempt accounting,
cancellation, or crash recovery. The strict 92AT mapped-byte claim remains
REJECT/HOLD; the local-container provenance claim remains unissued.

`INERT_CONTAINER_SMOKE=PASS`
`INERT_CONTAINER_COUNT=1`
`INERT_CONTAINER_REMAINS=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`LOCAL_CONTAINER_LAUNCH_CONTRACT_FROZEN=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
