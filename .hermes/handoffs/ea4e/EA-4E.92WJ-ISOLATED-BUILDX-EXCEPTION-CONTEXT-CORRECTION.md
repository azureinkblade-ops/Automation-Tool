# EA-4E.92WJ Isolated Buildx exception-context correction

Date: 2026-11-02 (America/Phoenix)
Status: SOURCE-ONLY CORRECTION / NEW REVIEW AND NATIVE RUN HOLD

The independent 92WI review found that the isolated launch `OSError` survived
in the fixed denial's `__context__`. The isolated denial is now raised only
after leaving the `except` block. Focused synthetic checks assert that both
`__context__` and `__cause__` are absent, that a case variant of the pinned
Windows root passes only the fixed spelling to the child, and that ordinary
Docker launch errors retain their prior behavior. The focused and shared
fake-only suite passed: 115 tests on worktree source.

This correction has not received a new independent review. The isolated
Buildx launcher remains HOLD for child-process/deadline containment, stable
plugin identity through launch, and independent builder-locality proof. No
Docker, Buildx, container, build, model, GPU, receiver, handoff, or production
action ran. Private model bytes and preserved Docker runtime directories
remain untouched. All native and production gates HOLD.
