# EA-4E.92JC provisional Kilo launch-spec candidate

Status: NON-LIVE PROPOSAL / NO CREATE OR START AUTHORITY.
Governing predecessor: `249aaf4d3c0c2993a50ce5e63e0fe36258290765`.

The versioned candidate binds one reserved fake Kilo attempt to its image
index/manifest and platform, exact entrypoint/argv, non-root user, workdir,
environment, reviewed input/runtime mount sources, isolated network name,
container labels/name, cleanup-owner label, and proposed host limits. The
spec hash covers the complete proposal. Verification rebuilds it from the
reserved intent and rechecks the prepared bytes, denying any modified field
even if a caller rewrites the supplied hash.

The 92JB supplemental host-policy review now reads the same proposed numeric
limits and security settings from this spec module. This prevents those two
non-live contracts from silently diverging. The candidate explicitly has
`create_authorized=false`, `launch_authorized=false`, and
`provenance_checked=false`. It contains only the dummy local credential class.

Focused builder/review/input tests: 29 passed. Adjacent fake-only Kilo and
claim/observation suites: 157 passed. No Docker create/start/inspect, real
Kilo/OpenCode receiver, provider/model call, GPU, or production activation
occurred in this checkpoint.

The limits and mount policy remain proposals, not a frozen qualified Docker
create contract. The actual daemon adapter, all effective settings/labels,
prestart and poststart observation, owner/reconciliation, and result delivery
are still open. An uncertain create cannot be retried with a new staging root
or container name; a future owner must reconcile the same attempt/spec.
The strict 92AT mapped-byte profile remains HOLD. Production remains HOLD.
