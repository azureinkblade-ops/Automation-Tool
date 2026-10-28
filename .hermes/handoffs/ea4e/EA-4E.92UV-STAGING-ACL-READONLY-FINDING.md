# EA-4E.92UV staging ACL read-only finding

Date: 2026-10-28 (America/Phoenix)
Status: HOST PRIVACY GATE / NATIVE HOLD / PRODUCTION HOLD

A read-only Windows ACL and free-space inspection of this worktree's
`output` directory found approximately 89.5 GB free on the containing
volume. The directory inherits modify access for several additional
principals, including a sandbox-users group. It is not qualified as a
private destination for a model-containing build-context tar. Raw SIDs
and account details are intentionally not copied into this handoff.

No ACL, directory, model file, Docker image, container, receiver, or
production state was changed. The source-reviewed 92UT staging helper
must not be run on real model bytes into this inherited `output` ACL.
An exact, separately governed setup and verification of a private staging
directory is required before real-byte staging, along with storage
budgeting and a reviewed build launcher. Production remains HOLD.
