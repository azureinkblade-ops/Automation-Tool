# EA-4E.92DG Kilo Linux image packaging

Status: NON-LIVE IMAGE BUILD PASS / RUNTIME QUALIFICATION HOLD
Baseline: `0dcff73559388c65274bac564b2b457c9861c9a4`
Date: 2026-10-06 (America/Phoenix)

Docker Desktop server reported Linux x86_64, version 29.6.2. No Kilo or
OpenCode image was already present. The local receiver adapters still pin
Windows executables, so Kilo was selected first for separate Linux-image
qualification. OpenCode was not changed or qualified by this checkpoint.

The official Kilo v7.8.3 `kilo-linux-x64.tar.gz` release asset was acquired
from GitHub. The GitHub release API reported SHA-256
`43c32cc25e09f2c8ae82faf480f482fb7de1f34ec5047edfde86158681ccb6bc`;
the 64,753,008-byte local archive matched. Its 423 paths contained no
absolute path, parent traversal, or symlink entry. The archive is retained
under ignored output, not tracked as source.

The provisional Dockerfile at
`tools/hermes_core/container_images/kilo_7_8_3/Dockerfile` pins the
Linux/amd64 Debian Bookworm slim base manifest
`sha256:a4672c0cb26fbdde88e38fa2dfb6c681942306680e41e4378b28770b6e79ee91`
and verifies the Kilo archive hash during build. Build steps ran with
`--network=none`; the daemon fetched the pinned base layer before those
steps. The warning-free second build produced local image
`hermes/kilo:7.8.3-linux-amd64-provisional` with image ID
`sha256:cf003ba6e84cfd0fa8c2951dfe44454e25f9cf5e42eb6bf3ba82349b26b99120`.
Image metadata: linux/amd64, user 65532:65532, entrypoint `/opt/kilo/kilo`,
workdir `/work`, size 94,359,312 bytes. No container was created or run.

This is packaging provenance, not `LOCAL_CONTAINER_PROVENANCE_CHECKED`.
The runtime still needs a reviewed writable home/workspace, exact config and
credential delivery, network route, resource ceilings, timeout/output cap,
one-attempt accounting, cancellation, cleanup, and daemon observation.
No real Kilo process or model call is authorized. The strict 92AT mapped-byte
claim remains REJECT/HOLD, independently of this local-container profile.

Official release: https://github.com/Kilo-Org/kilocode/releases/tag/v7.8.3

`KILO_LINUX_ARCHIVE_HASH_MATCH=YES`
`PROVISIONAL_IMAGE_BUILD=PASS`
`KILO_CONTAINER_RUNTIME_QUALIFIED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`CONTAINERS_CREATED=0`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
