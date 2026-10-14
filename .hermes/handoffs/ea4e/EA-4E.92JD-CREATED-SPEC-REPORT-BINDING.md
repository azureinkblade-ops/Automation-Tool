# EA-4E.92JD created-spec report binding

Status: NON-LIVE REPORT COMPARISON / START AUTHORITY: NO.
Governing predecessor: `8c732d58ed71a206fdc8d87609d891c9b5be415b`.

The 92IJ created-container record now exposes the container and image
observation digests it already persisted. The 92JB host-policy review requires
freshly supplied metadata bytes to match those digests. A new pure 92JD
comparison additionally rebuilds and verifies the 92JC spec, then checks the
reported container name, attempt/candidate/profile labels, command, user,
workdir, bind mounts, restart policy, namespace defaults, ulimits, and DNS
settings. A match is named `CREATE_SPEC_REVIEW_ONLY_START_DENIED`.

This closes the previous gap where the same container/network IDs could be
accompanied by a different created-container metadata payload at review time.
Focused synthetic tests: 36 passed. They include drift present when recorded,
post-record mutation, and a caller-modified spec with a recomputed hash.

The record and review still rely on caller-supplied inspect data. They do not
independently query Docker, attest image bytes, establish socket ownership,
or authorize create/start. Gateway/receiver identity, full effective daemon
settings, the one-shot owner, cancellation/reconciliation, and real Kilo or
OpenCode qualification remain open. Strict 92AT is unchanged; production is
HOLD. No Docker object, receiver/model call, GPU, or activation occurred.
