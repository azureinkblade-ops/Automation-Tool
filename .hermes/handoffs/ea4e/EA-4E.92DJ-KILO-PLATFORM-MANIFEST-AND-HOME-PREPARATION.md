# EA-4E.92DJ Kilo platform manifest and home preparation

Status: NON-LIVE IMAGE PREPARATION PASS / CONTAINER LAUNCH HOLD
Baseline: `6d3c91de3eb7464b868451eba0bb7b0b420681c4`
Date: 2026-10-06 (America/Phoenix)

The provisional Dockerfile now creates `/tmp/kilo-home` and `/work` owned by
UID:GID 65532:65532. This prepares paths for a future non-root launch; it
does not prove that a read-only root filesystem with separately mounted
scratch has correct runtime permissions. No container was created or run.

The warning-free, Linux/amd64 build used the same pinned Debian base and
verified Kilo v7.8.3 archive. Build steps ran with `--network=none`. It
produced three distinct identities:

- amd64 image manifest: `sha256:2eaab2a5675726461630106859873c29f03641c142ae47c6b6060aebc611504d`
- local multi-platform index: `sha256:c170379623cd8d16feb2c15fcdd473c401275336dc046fe72a5a5075c3474303`
- config blob: `sha256:e41f1264154d91ccb4176b056654002165ca4ed90872c12b2bda4e670ce6e910`

Default `docker image inspect` reported the index as `Id`; inspection with
`--platform linux/amd64` reported the amd64 manifest as `Id`. The 92DH
checker was repinned to the latter. A fake test now denies the index digest
as an image ID. The previous 92DH match remains historical metadata evidence
for the previous image, not proof of this image's runtime qualification.

Verification:

- `docker build --check --platform linux/amd64`: no warnings.
- Focused image-admission, Kilo adapter/binding, production wiring, and app
  host regressions: 194 passed, 0 failed.
- Read-only `docker image inspect --platform linux/amd64` fed to the pure
  checker: `MATCH`, with `receiver_executed=False` and
  `provenance_checked=False`.

The admission checker still trusts supplied daemon metadata and cannot
establish that a created container used the reviewed launch spec or that a
running receiver consumed the intended configuration. 92DI's network,
credentials, scratch mounts, limits, durable accounting, cancellation, and
daemon-observation gates remain open. No real Kilo/model call is authorized.

`PLATFORM_MANIFEST_METADATA_ADMISSION=PASS`
`LOCAL_CONTAINER_LAUNCH_CONTRACT_FROZEN=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`CONTAINER_STARTED=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
