# EA-4E.92WH Isolated Buildx error-bound candidate

Date: 2026-11-02 (America/Phoenix)
Status: SOURCE-ONLY CORRECTION / NATIVE AND PRODUCTION HOLD

After the independent 92WG HOLD review, this narrow correction fixes two
isolation findings in the opt-in path. The isolated environment now accepts
only a case-insensitive match to `C:\Windows` for `SYSTEMROOT` and passes the
pinned spelling to the child. An `OSError` from isolated subprocess creation
now becomes a fixed `SmokeDenied` category without exposing its raw path.
Ordinary Docker subprocess-start behavior is unchanged. Two new synthetic
tests cover a different root and path-bearing launch error. The focused and
shared fake-only suite passed: 113 tests on the worktree source.

The other 92WG HOLD findings remain: no Buildx child-process containment or
hard wall bound, no stable plugin identity through launch, and no independent
proof of builder/daemon locality. The environment and error correction has
not received a new independent review. No private plugin setup, Docker,
Buildx, container, build, model, GPU, receiver, handoff, or production action
ran. Private model bytes and Docker runtime backups remain untouched. All
native build, model, handoff, and production gates HOLD.
