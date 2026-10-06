# EA-4E.92DL pre-start image binding

Status: NON-LIVE PURE BINDING PASS / LAUNCH CONTRACT HOLD
Baseline: `49de0e56d8d38f88394f41005c1c7a39c5c46495`
Date: 2026-10-06 (America/Phoenix)

92DK's inert smoke showed that a created container's `.Image` field reports
the local image index while platform-specific image inspection reports the
Linux/amd64 manifest. The new pure `inspect_prestart_image_binding()` binds
those distinct observations without creating or starting a container. It
requires the existing platform-manifest admission result, a matching local
`RepoDigests` index reference, a `created` container state, and the exact
container `.Image` index. Wrong or malformed inputs deny.

The function has no Docker, subprocess, network, issuer, activation, store,
or model capability. Both success flags remain false: matching these
metadata does not prove that the launch spec, credentials, mounts, network,
and limits were reviewed, nor that a receiver ran. A fake created-container
record based on 92DK's observed index bound to read-only real image metadata.

Verification: 206 focused image-admission/Kilo/binding/wiring/app-host tests
passed, 0 failed. The previously approved inert container had already been
removed; this checkpoint made no container or receiver invocation.

Next: freeze and fake-test the complete created-container effective-config
checker, including exact entrypoint/argv, UID, mounts, network, security
options, resources, labels, and attempt identity. The Linux profile/config
and credentials remain unresolved. A real receiver/model run needs separate
bounded authorization.

`PRESTART_INDEX_MANIFEST_BINDING=PASS_FAKE_ONLY`
`LOCAL_CONTAINER_LAUNCH_CONTRACT_FROZEN=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
