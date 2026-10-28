# EA-4E.92VF verified-context build policy candidate

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CORRECTION / INDEPENDENT REVIEW REQUIRED / NATIVE HOLD / PRODUCTION HOLD

The build policy now opens the staged tar through the existing
PAX-compatible consumer, which verifies exact archive members, hashes,
recipe bytes, padding, and framing while holding the same Windows file
handle against writers. The policy retains that handle within the
context-manager lifetime and checks that its file identity still matches
the path. It also checks the committed Dockerfile against the generated
recipe and the pinned base-image reference before producing arguments.

Strict synthetic/source tests passed (33/33). They include rejection of
a same-named non-archive, a directory, wrong location/name, changed
recipe, and a preexisting image-ID output. No real model bytes, Docker,
build, GPU, receiver, or agent handoff ran.

This is not a native build launcher and does not close the earlier HOLD.
The image-ID output has only a point-in-time collision check, not an
exclusive reservation. The private staging ACL and returned-path
provenance require a native preflight; builder locality, offline base
resolution, process limits, deadlines, output capture, and daemon-side
reconciliation remain unverified. A new independent source review and
separate exact native authorization remain required. Production HOLD.
