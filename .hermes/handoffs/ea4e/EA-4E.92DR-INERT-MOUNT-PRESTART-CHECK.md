# EA-4E.92DR inert mount prestart check

Status: FAKE-ONLY QUALIFIED / MOUNT PROBE NOT AUTHORIZED
Baseline: `b050d8720695fcc8aa93b9b1c8515a6b89714df3`
Date: 2026-10-06 (America/Phoenix)

Added `local_kilo_inert_mount_check.py` as a pure comparison of proposed
created-container metadata. It reuses the 92DL image index/manifest check,
freezes a `/bin/sh -ec` command that reads only the dummy config/profile
files and writes a constant runtime marker, and rejects an unexpected user,
environment, port, network mode, privilege, capability, namespace, resource
limit, mount count/type/source/destination, or mount write mode. It cannot
create or start a container and its result grants no execution authority.

The caller-supplied host source strings are compared exactly. This is not
host-path provenance or a proof that the Docker daemon's effective mounts
have been observed. The fake fixture uses an empty container environment;
if a real created container inherits image environment variables or Docker
reports a different metadata shape, this check returns HOLD/DENY until the
observed shape is separately reviewed. Do not loosen it during a one-shot
probe or infer that a fake match authorizes start.

Verification: 67 passed, 0 failed across the 92DR, 92DP, 92DN, 92DH, and
fake-provider-accounting focused suites. No Docker command, receiver,
provider, model, network, GPU, or ComfyUI call was made. The separately
proposed 92DQ inert mount probe still requires explicit one-shot approval.

`PROBE_AUTHORIZED=NO`
`NEW_CONTAINER_CREATED=NO`
`KILO_RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
