# EA-4E.92DT one-shot inert mount probe

Status: INERT FILE-DELIVERY PROBE PASS / ONE-SHOT APPROVAL CONSUMED
Baseline: `04f3d9bcb5d800e71713d339f09e6c712766472c`
Date: 2026-10-06 (America/Phoenix)

The operator explicitly confirmed one bounded inert Docker mount probe after
the 92DQ proposal and 92DR/92DS fake-only checks. This approval covered
one container, a fixed `/bin/sh -ec` marker command, the two temporary
dummy-file mounts, no network, non-root execution, a read-only rootfs,
bounded resources, and removal of only that stopped container. It did not
authorize Kilo, a model, another container, or production activation.

Preflight matched the pinned linux/amd64 platform image. 92DP created a
fresh system-temp root with separate `input` and `runtime` dummy copies:

`C:\Users\David\AppData\Local\Temp\ea4e92dt-a062935ff6c049caa07d40cf72112db4`

The manifest remains at `manifest.json` in that root, SHA-256:
`eb6605d1e0feb7ea50d93ecf90ffe68e1b979b7d3579748691d1a27f79ee01ea`.
Those temporary files were not deleted. No repository, user-home,
credential, or Docker-socket path was mounted.

Exactly one container was created, ID:
`90c9e99e08ea5c7d13bf97c11a3ba79593677c7b370e45c6e27554e2d66a8ced`.
Before start, 92DR/92DS returned `MATCH / INERT_PRESTART_METADATA_MATCHED`;
the container identity matched, its status was `created`, and it had
exactly two bind mounts. It then started once, exited 0, and remained
stopped for verification. The runtime marker matched
`EA4E_MOUNT_OK\n` (SHA-256
`193b0e7412085f89f26595cb8273edf61c14befc479409789a532671b8058141`).
Both dummy config/profile copies still matched the planned SHA-256 values.
Container logs contained zero bytes. The exact stopped container was
removed normally; a follow-up listing found no remaining container with
that ID. The temporary manifest remained present.

The bounded 92DR/92DP/92DN/92DH/fake-provider regression set was rerun
after the probe: 72 passed, 0 failed.

This qualifies only the inert local file-delivery and non-root writable
runtime-path behavior for this Docker/image/environment combination.
It does not show Kilo config parsing, receiver launch, request admission,
network peer identity, dynamic gateway-body binding, credential isolation,
model invocation, or production readiness. The local-Docker alternative
still has a weaker trust model than the strict 92AT mapped-byte route;
92AT remains REJECT/HOLD. A real receiver probe needs a new, separately
bounded authorization and its own preflight.

`ONE_SHOT_APPROVAL_CONSUMED=YES`
`CONTAINERS_CREATED=1`
`CONTAINERS_STARTED=1`
`CONTAINER_EXIT=0`
`CONTAINER_REMOVED=YES`
`TEMP_FILES_RETAINED=YES`
`KILO_RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_ACTIVATED=NO`
`PRODUCTION_READY=NO`
