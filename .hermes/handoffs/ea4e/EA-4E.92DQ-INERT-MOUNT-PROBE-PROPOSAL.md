# EA-4E.92DQ inert mount probe proposal

Status: NON-LIVE DESIGN ONLY / NEW PROBE NOT AUTHORIZED
Baseline: `a8ed8aad0b9b2ddbeaa85332ade68d575e3eb370`
Date: 2026-10-06 (America/Phoenix)

92DP prepares two hash-checked copies of dummy Kilo config/profile under
a new system-temp root: `input` and `runtime`. No container has consumed
them. The one `/bin/true` smoke approved for 92DK was used and cannot be
reused as authorization for another container.

## Proposed one-container scope

If separately approved, prepare one fresh 92DP temp root, then create one
container from the pinned Linux/amd64 image. Before start, inspect and deny
unless its effective configuration matches all of the following:

- entrypoint `/bin/sh` with one fixed, reviewable command; no Kilo binary;
- UID:GID 65532:65532, read-only rootfs, no privileged mode, no added
  capabilities, no-new-privileges, bounded CPU/memory/pids;
- `network=none`, no published ports, no Docker socket, no host PID/IPC;
- exactly two host bind mounts: the new `input` directory read-only at
  `/reviewed-input`, and its separate `runtime` directory writable at
  `/tmp/kilo-home`; no repository, home, credential, or other mount;
- the same local image index and amd64 manifest relationship qualified in
  92DL, with one unique container identity.

The fixed command would read the dummy config/profile in both locations,
write only a constant marker under `/tmp/kilo-home`, and exit. The marker
tests real write access; no provider, receiver, or model command is allowed.
After start, require exit 0 and recheck the reviewed `input` SHA-256 values.
Record the runtime files' hashes and marker result separately, then remove
only the exact stopped probe container. Temp files must be retained unless
their cleanup is explicitly included in the approval; no unrelated files
or containers may be touched.

If Docker Desktop's Windows bind-mount ownership prevents the non-root
write, report HOLD. Do not switch to root, relax permissions, add a broad
mount, or retry with another container under this one-shot proposal.

This probe could qualify only the inert file-delivery path. It would not
prove Kilo's config parsing or rewrite behavior, network peer identity,
one-request gateway admission, real credentials, or model execution.
Those are later, separate boundaries. No production activation follows
from a successful mount probe.

`PROBE_AUTHORIZED=NO`
`NEW_CONTAINER_CREATED=NO`
`KILO_RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
