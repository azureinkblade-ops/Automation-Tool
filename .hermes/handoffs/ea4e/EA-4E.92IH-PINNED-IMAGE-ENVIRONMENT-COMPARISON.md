# EA-4E.92IH Pinned Image Environment Comparison

Status: NON-LIVE CORRECTION / START DENIED.
Baseline: `28f1b6e422a84514efb1be98a7b4fd764631fc39`.

The 92IG comparator formerly accepted arbitrary extra environment keys so
long as candidate keys matched. It now requires the pinned image's observed
`Config.Env` and the created container's `Config.Env` to have unique keys.
The expected effective environment is exactly the image environment with
the candidate's explicit key overrides. Missing image metadata, duplicate
keys, changed candidate values, and added keys such as `OPENAI_API_KEY` deny.

The synthetic focused suite passed 21 tests; the affected
92DH/DP/DR/92H/92I ladder passed 207 tests, zero failures. Post-commit
verification is separate. This is not a daemon observation or proof that the
image itself is trustworthy outside the accepted local-container profile.

The comparator still reports candidate metadata only and denies start.
Network/peer ownership, tmpfs options, resource/security limits, retained
output, and a one-shot execution owner remain unresolved. No Kilo/OpenCode
receiver, gateway, model, credential, Docker object, or production activation
was used in this correction. Strict 92AT mapped-byte proof remains HOLD.
