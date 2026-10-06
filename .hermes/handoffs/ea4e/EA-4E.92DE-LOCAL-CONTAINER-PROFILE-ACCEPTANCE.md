# EA-4E.92DE local-container profile acceptance

Status: OPERATOR ACCEPTED ALTERNATIVE THREAT MODEL / IMPLEMENTATION NOT YET QUALIFIED
Baseline: `a0ef229d47e4068e9502e8768ff7c817c11cf8b2`
Decision date: 2026-10-06 (America/Phoenix)

The operator approved the faster alternative proposed in 92DD. This approval
accepts a separate local-container assurance profile which trusts the current
Windows PC's administrators, SYSTEM, Docker Desktop/daemon, Docker-control
account, local Hermes authority/store, and receiver image publisher. An
attacker with any of those privileges is outside this alternative profile.
It is therefore not an independent defense against a local administrator.

The positive claim, if later qualified, is named
`LOCAL_CONTAINER_PROVENANCE_CHECKED`. It must be based on a pinned,
platform-specific OCI image digest, reviewed launch configuration, and
observation from the trusted local daemon. It is not exact mapped-image-byte
attestation and does not satisfy 92AT `VERIFIED_SUSPENDED`. The 92AT/92CZ
strict profile remains frozen at REJECT/HOLD and must not be overwritten,
renamed, or reported green because this alternative was approved.

Acceptance is a design decision only. The installed Kilo/OpenCode adapters
still launch local binaries. No Docker adapter, qualified image, frozen
container contract, or running Docker daemon has been established. The
application remains default-disabled for production. No process, receiver,
provider, or model action is authorized by this decision.

Next gates, in order:

1. Inventory Docker daemon/platform and candidate receiver image without
   running a receiver. Pin exact image digest and dependency closure.
2. Freeze a versioned container launch/admission contract, including
   command, mounts, environment, network, resources, one-attempt accounting,
   output bounds, cancellation, cleanup, and provenance observation.
3. Implement fake-only denial tests and a narrow adapter. Verify existing
   strict-path tests remain unchanged and default production activation is
   still off.
4. Separately authorize an inert container integration probe. A later real
   Kilo/OpenCode model call requires its own bounded authorization.

`ALTERNATIVE_THREAT_MODEL_ACCEPTED=YES`
`LOCAL_CONTAINER_PROVENANCE_CONTRACT_FROZEN=NO`
`DOCKER_RECEIVER_IMPLEMENTED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
`LIVE_ACTIVITY=0`
