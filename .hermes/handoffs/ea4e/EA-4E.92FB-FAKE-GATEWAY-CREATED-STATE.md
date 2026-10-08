# EA-4E.92FB Fake Gateway Created-State Gate

Status: SYNTHETIC CREATED-STATE PASS / REAL CREATED SNAPSHOT HOLD
Baseline before this change: `487ada5d353396ce6b96ba76a2f97953495d76ba`
Date: 2026-10-08 (America/Phoenix)

The pure created-state gate compares one exact internal bridge network and
two never-started container records against the canonical fake probe plan.
It checks returned IDs, image and entrypoint/command configuration, non-root
read-only host policy, resource limits, no mounts/devices/published ports,
single intended network attachment, and the gateway alias. A created endpoint
may have an empty `NetworkID`, consistent with the earlier 92EM diagnostic;
a wrong nonempty ID is denied. The gate returns `start_authorized=False`.

28 synthetic plan/preflight/created tests passed with zero failures. No Docker
network or container was created for this checkpoint. The fixture does not
establish what a new real fake-gateway container will report in its `Image` or
`Config.Image` fields. Any actual diagnostic must stop before start on a
mismatch, preserve bounded sanitized evidence, and clean exact created IDs.
Running peer and request evidence remains separate.

`CREATED_CHECK_FAKE_ONLY=PASS`
`REAL_CREATED_SNAPSHOT_OBSERVED=NO`
`CONTAINER_STARTED=NO`
`PEER_QUALIFIED=NO`
`PRODUCTION_READY=NO`
