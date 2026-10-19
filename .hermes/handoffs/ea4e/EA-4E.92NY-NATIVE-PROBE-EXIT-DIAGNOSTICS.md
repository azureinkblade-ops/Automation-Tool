# EA-4E.92NY native probe exit diagnostics

Status: NON-LIVE DIAGNOSTIC REMEDIATION / NATIVE RETRY HOLD.
Governing parent: `30292523346c7369b22ee19affb83a8becdd90fd`.

The 92NX attempt remains HOLD with exit `1` and an unknown denial stage.
This checkpoint does not reinterpret or repeat it.

The fixture now returns stable nonzero process exit codes when its hidden
console cannot be captured: `10` input, `11` deadline, `12` operator token,
`13` privilege enable, `14` pipe create, `15` descriptor readback, and `16`
privilege restoration. An unrecognized failure returns `17`; an incomplete
command line remains `2`. A candidate structural readback still returns `0`
only after pipe close and privilege restoration. These codes classify a
future probe stage, not successful security qualification.

The inert CLI and adjacent 92NT/92NO tests passed 27/27. No test invoked
the native mode or a protected pipe. A new executable built from this source
requires a new hash, exact one-shot authorization, and operator/UAC review
before any native execution. The 92NK client-rights and issuer gates remain
open. No Docker mutation, Kilo/OpenCode receiver, model, production
activation, GPU, or ComfyUI action occurred.
