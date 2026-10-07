# EA-4E.92DZ inert peer helper prepared

Status: OFFLINE-STYLE IMAGE BUILD PASS / TWO-CONTAINER PROBE NOT AUTHORIZED
Baseline: `4514dd415222139b48b43b50a9ec950484d91d08`
Date: 2026-10-07 (America/Phoenix)

The cached `registry.librechat.ai/danny-avila/librechat-dev` Linux/amd64 image
was present with immutable local ID / repo digest
`sha256:3144a862c5947599f5eeab3f9dfde33a690fa98d01065b9d66576da43a692561`.
Its metadata specifies Node 24.16.0 and a `node` user. A narrow Dockerfile
uses that digest, copies only `marker.js`, and overrides the entrypoint with
`node /opt/ea4e-peer/marker.js`. It has no `RUN` step and does not invoke the
base image's LibreChat entrypoint.

The helper has two fixed modes. `gateway` listens on port 8181, serves one
constant `GET /marker` response, and records only the accepted socket's
remote address. `client` requests that fixed path from
`ea4e-peer-gateway:8181`, requires the constant marker, and exits. There is
no prompt, credential, Kilo command, model endpoint, or provider call. The
local handler tests passed 2/2 without opening a socket.

The provisional image was built with `--pull=false --network=none` from the
cached base. Build output showed no layer download or `RUN` step, but these
flags do not independently prove that the builder made zero metadata network
requests. The first local image was `hermes/ea4e-peer-helper:92dz-provisional`,
ID `sha256:db376403e4d5bb681eae77bc09d8f91faa980799e501c2b21a11612a035d99ac`.
After the source-only commit, a build from the committed tree produced ID
`sha256:de6495938a8fb3fb1745f1d955d0b56b0d3dd3283bd8f6e20c7ad020d31c72f9`.
The source SHA-256 values below stayed identical; the reason the image ID
changed was not established. The original ID is no longer inspectable in
the local image store. Reproducible image identity is **not** qualified.
The mutable tag is not a probe authority; the exact current image ID is a
candidate for a separately reviewed probe. Read-only inspection
of the current image reported Linux/amd64, user `node`, and the fixed
entrypoint. It also inherited `3080/tcp` in image `ExposedPorts` from the
base; that does not publish a port, but a future container must still
have an empty daemon-reported published-port mapping. No helper container
was started.

Source SHA-256 values (working files at preparation time):
- `marker.js`: `cda206fe636f57d509cc8251f896298b2917e79a01570290b2b66ec933243667`
- `Dockerfile`: `151a1b9e55d27481d597f07942ac52e791cfabbeff76ade616b9a639ff1e68a7`

## Proposed one-shot Docker peer observation, not yet authorized

Only after that exact immutable image ID is selected and rechecked, a
separate approval could cover one new per-attempt `--internal` bridge and
exactly two containers
from the pinned helper image (one gateway and one client), no published ports,
no bind mounts, no secrets, no host networking, non-root execution, read-only
root filesystems, dropped capabilities, bounded CPU/memory/pids/output, and
one fixed marker request. The gateway would report the accepted socket peer;
the trusted daemon's fresh network/container inspection would be compared
with 92DY. Require a single membership and a matching receiver endpoint;
otherwise report HOLD. Stop after one request or a short timeout, then
remove only the exact stopped probe containers and the exact owned network.
No Kilo binary, model, or production activation belongs in this probe.

The current `--internal` network proposal does not exclude host access to
container IPs; the marker has no secrets and this probe would test the
candidate address-binding behavior only under the accepted local trust
model. A successful marker exchange would not qualify the dynamic gateway,
receiver invocation, upstream send, or strict 92AT mapped-byte proof.

`HELPER_SOURCE_TESTS=2_PASS`
`PROVISIONAL_IMAGE_BUILT=YES`
`REPRODUCIBLE_IMAGE_ID=NO`
`FROZEN_PROBE_IMAGE=NO`
`HELPER_CONTAINERS_STARTED=0`
`PEER_PROBE_AUTHORIZED=NO`
`KILO_RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
