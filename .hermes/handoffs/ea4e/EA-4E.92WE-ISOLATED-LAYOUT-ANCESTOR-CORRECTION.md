# EA-4E.92WE Isolated layout ancestor correction

Date: 2026-10-31 (America/Phoenix)
Status: SOURCE-ONLY CORRECTION / NATIVE SETUP AND RUN HOLD

The 92WD independent review found that the 92WC value-only policy checked
only immediate path components. The policy now checks every ancestor for
reparse/symlink status, requires canonical local drive paths, and denies
parent traversal aliases. Two focused synthetic cases were added. Seven
focused synthetic tests pass on staged-identical worktree source with the
repository live-test setup excluded.

This correction addresses only the path-identity finding at validation time.
It does not bind the plugin bytes to a later launch, prevent replacement
between checks, prove private ACLs, enforce the exact returned environment,
contain a process tree, or prove Docker locality/read-only behavior. The
92WC layout candidate and 92VZ standalone version probe remain on HOLD for
native use. A full reviewed launcher and a separate exact one-shot
authorization are still required.

No plugin was copied or run. No Docker/Buildx executable, container, archive
upload, build, model, GPU, receiver, handoff, or production action ran. The
private model archive and preserved Docker runtime directories are untouched.
All native build, model, handoff, and production gates HOLD.
