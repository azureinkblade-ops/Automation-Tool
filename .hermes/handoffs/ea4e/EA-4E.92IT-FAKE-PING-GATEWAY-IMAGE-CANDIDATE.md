# EA-4E.92IT Fake Ping Gateway Image Candidate

Status: BUILT / INSPECTED / NOT STARTED / NOT RECEIVER-QUALIFIED.
Source commit: `7c78d484e2c3a334570bcbb21866f86db599332f`.
User approved one offline image build; this is not authorization to start it.

Docker Desktop Linux engine 29.6.2 was started with user approval. Existing
LibreChat containers auto-started under their restart policies; no EA-4E
container was created or started. At initial inspection, `admin-panel` was
restarting. Those pre-existing containers were not changed or cleaned up.

The build used the committed versioned context only:

```text
docker build --pull=false --network=none --no-cache --platform linux/amd64
  --label hermes.ea4e.source_commit=7c78d484e2c3a334570bcbb21866f86db599332f
  --tag ea4e92it-kilo-ping-gateway:7c78d48
  tools/hermes_core/container_images/ea4e92io_kilo_ping_gateway
```

The pinned local base was
`sha256:3144a862c5947599f5eeab3f9dfde33a690fa98d01065b9d66576da43a692561`
(`linux/amd64`, Node 24.16.0). The build log shows only WORKDIR and COPY
after that base. Source SHA-256 before/after build:

```ini
gateway.js=7BE2F15B00FA7A79D85F3E588400CDE20D9BAF6EBEBC29AC7C1C3E6BE1726CA0
Dockerfile=EF80CD47A0A3C5821361693B28DC00C8BD0C96633CAA37790182E8E0CBDFBF4B
image_index=sha256:afdd2f974bb91d8b3c9bc8da6dd2ac4c2667d4fe1c4e756b0e818e9eff5cd511
image_config=sha256:1d7d9fde5afa527ca3d109c7265d1609f11c7e048a9a03e39e95dd3338c8765b
platform_manifest=sha256:cadf00b4b0f402eeca51379b044cf4990835c6701847be4b09d75acb32662a73
```

Read-only inspect confirmed user `node`, entrypoint
`node /opt/ea4e-ping-gateway/gateway.js`, workdir
`/opt/ea4e-ping-gateway`, source-commit label, no provider credentials in
image environment, and no containers based on this image. The base image
inherits `3080/tcp` as an exposed port; this is not a published host port.
`--pull=false` and `--network=none` were requested, but this record does not
claim independently observed zero build-time network traffic.

This is a local image candidate, not proof of the exact copied file bytes
inside a running image, actual SDK compatibility, Docker peer attribution,
authorization, receiver/model use, result return, or production readiness.
No Kilo/OpenCode receiver, model, GPU/ComfyUI, or EA production activation
was invoked. Strict 92AT mapped-byte proof remains HOLD.
