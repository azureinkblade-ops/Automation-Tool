# EA-4E.92WL Isolated Buildx layout-context correction

Date: 2026-11-02 (America/Phoenix)
Status: SOURCE-ONLY CORRECTION / NEW REVIEW AND NATIVE RUN HOLD

The independent 92WK review found that fixed layout denials retained raw
filesystem `OSError` context. `_names` and `_sha256` now raise their fixed
`LayoutDenied` categories only after leaving the error handler. New synthetic
tests cover inventory and plugin-read failures and traverse the Docker
transport denial chain to check that no raw `OSError` or private path remains.
The focused suite passed 20 tests; the shared fake-only suite passed 118
tests on worktree source. These tests do not prove native Windows behavior.

This correction has not received a new independent review. The isolated
Buildx launcher remains HOLD for child-process/deadline containment, stable
plugin identity through launch, and independent builder-locality proof. No
Docker, Buildx, container, build, model, GPU, receiver, handoff, or production
action ran. Private model bytes and Docker runtime backups remain untouched.
All native and production gates HOLD.
