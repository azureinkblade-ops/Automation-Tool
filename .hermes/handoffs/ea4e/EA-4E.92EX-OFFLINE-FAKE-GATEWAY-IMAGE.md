# EA-4E.92EX Offline Fake Gateway Image

Status: OFFLINE IMAGE BUILD PASS / CONTAINER AND RECEIVER HOLD
Source commit: `56c95e7fd76a145943002225171e3c58ae8b0011`
Date: 2026-10-08 (America/Phoenix)

One local Linux/amd64 fake-gateway image was built with `--pull=false` and
`--network=none` from the committed 92EW Dockerfile. The pinned base image
`sha256:3144a862c5947599f5eeab3f9dfde33a690fa98d01065b9d66576da43a692561`
was cached before the build. The Dockerfile has no `RUN` step.

- Local tag: `ea4e92ex-fake-gateway:56c95e7`
- Linux/amd64 image manifest ID: `sha256:7d812fc364c8f4dd47e6b25f83d4074c212fa5ad348d4cda9251b8734557420b`
- Local manifest-list digest: `sha256:ba59552b483c3fb3a13880da33197f29cada670b80c38862eaa587bed84c3787`
- Config ID: `sha256:565a7e6e1c1a76143376677a61a140c7d3cceb15ad6f02b6a09387399b1e040d`
- Gateway source SHA-256: `F33CF444D18883D8604E07831FCBE888A715C58DF5F445B98FCB56121C8AD494`
- Dockerfile SHA-256: `E2BA8EE5CF158400026942B7A756E9B07514B9D9D63BF7EADB6769B01AA3BC48`

Read-only inspect showed `User=node`, entrypoint
`node /opt/ea4e-fake-gateway/gateway.js`, and no container with this image.
The base image contributes an `ExposedPorts` metadata entry for `3080/tcp`;
this does **not** publish a host port, but a later probe must still assert no
actual port bindings. This build does not establish gateway event authenticity,
fresh Docker peer binding, durable one-send accounting, receiver admission, or
production readiness. No container, Kilo/OpenCode receiver, model, provider,
GPU, ComfyUI, or production activation was run.

Next: freeze and fake-test a one-shot container probe that verifies exact image,
private network, peer event, hold/release, and exact-ID cleanup. Any real
receiver/model execution remains separately governed.

`IMAGE_BUILT=YES`
`CONTAINER_STARTED=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
