# EA-4E.92ME app-owner package observation gate

Status: NON-LIVE QUALIFIED / PRODUCTION HOLD.
Parent baseline: `6b477c009a900669f70159d068b44d889a043c1a`.

The 92LQ/92LR native observation branch previously copied the package
hash from the launcher receipt into its process observation. Its positive
live resolution did not independently recheck package state. The owner
now requires an explicit process API and package API together for that
branch; the launcher-only observation branch requires `fake_only=True`.
Every native `resolve_live()` calls `observe_package(receipt)` and accepts
only an exact `AppPackageObservation` with the expected digest and literal
`complete=True`. Missing, malformed, incomplete, or changed package
observations move the owner to UNKNOWN before process identity is queried.
The check repeats on successive resolutions.

Changed: `tools/ea4e92lq_app_instance_owner.py` and
`tests/hermes_core/test_ea4e92lq_app_instance_owner.py`.
Focused: 41 passed, 0 failed. Adjacent owner/agent handoff and recovery:
118 passed, 0 failed, one inherited `app.py` invalid-escape SyntaxWarning.

This defines a fail-closed collaborator contract, not an installed
protected package observer. A caller-supplied fake observer is test-only.
No real launcher, app process, protected issuer, Docker mutation,
receiver/model, GPU, ComfyUI, or production activation was used. It does
not solve the strict 92AT mapped-image byte proof or qualify the local
container alternative for production.
