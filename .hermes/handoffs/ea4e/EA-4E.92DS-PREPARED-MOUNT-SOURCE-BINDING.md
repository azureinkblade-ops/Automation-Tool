# EA-4E.92DS prepared mount source binding

Status: FAKE-ONLY QUALIFIED / MOUNT PROBE NOT AUTHORIZED
Baseline: `d4ab2afa7b68f904d0f3b94e99afdc4705dd5032`
Date: 2026-10-06 (America/Phoenix)

The 92DR prestart metadata checker previously accepted caller-supplied
host source strings. It now derives those strings from the 92DP prepared
input manifest. Before comparing the container's two bind mounts, the
read-only verifier requires the expected manifest schema and disabled
launch flag, a resolved root under the system temp directory, distinct
input/runtime directories, the exact two planned file records, and
SHA-256 readback of both copies against the deterministic inert plan.
Unexpected links, changed dummy bytes, a forged manifest record, or a
different observed mount source are denied.

This check reads local files but does not create or start a container.
The manifest is not signed; a local actor with access to the temp files
could change them after verification. A fake metadata match is neither
host-path provenance nor proof of the daemon's effective mounts. The
actual created-container metadata shape and Windows bind behavior remain
unobserved. Do not weaken a mismatch during a one-shot probe.

Verification: 31 focused 92DR/92DP tests and 72 broader fake-only tests
passed, with zero failures. No Docker container, receiver,
provider, model, GPU, or ComfyUI action occurred. 92DQ still requires
separate one-shot approval.

`PROBE_AUTHORIZED=NO`
`NEW_CONTAINER_CREATED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
