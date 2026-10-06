# EA-4E.92DH local Kilo image metadata admission

Status: NON-LIVE PURE ADMISSION PASS / RUNTIME CONTRACT HOLD
Baseline: `4e6034a5592dca043c27c1d88ae855d92bea36b8`

The new `tools/hermes_core/local_kilo_image_admission.py` compares
daemon-reported image metadata against the provisional Kilo v7.8.3 image:
exact image ID, Linux/amd64, non-root UID:GID, fixed entrypoint, and workdir.
Any absent or mismatched field denies. A mutable tag cannot stand in for the
image ID. The result `MATCH` means only that this metadata matched; it always
reports `receiver_executed=False` and `provenance_checked=False`.

The module imports no Docker client and has no subprocess, shell, network,
model, issuer, activation, or store capability. It does not call or change
the existing Windows Kilo/OpenCode adapters or application wiring. It cannot
mint `LOCAL_CONTAINER_PROVENANCE_CHECKED` or 92AT `VERIFIED_SUSPENDED`.

Evidence:

- New focused fake tests: 15 passed.
- Existing Kilo adapter, pre-live binding, production wiring, and app-host
  tests plus new tests: 193 passed, 0 failed.
- Read-only `docker image inspect` of the provisional image returned `MATCH`
  with both execution and provenance flags false.
- No Kilo task container was created or run; no receiver or model invoked.

The remaining runtime contract must freeze exact run parameters, writable
scratch/home and workspace, config/credential delivery, network, resource
and output limits, one-attempt accounting, cancellation, cleanup, and
post-create daemon observations. Image metadata admission is a prerequisite,
not authorization or production readiness.

`IMAGE_METADATA_ADMISSION=PASS`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`DOCKER_RECEIVER_IMPLEMENTED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
`LIVE_ACTIVITY=0`
