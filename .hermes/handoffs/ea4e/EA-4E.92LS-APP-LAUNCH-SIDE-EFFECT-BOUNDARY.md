# EA-4E.92LS app-launch side-effect boundary

Status: SOURCE-ONLY REVIEW / NO APP LAUNCH / PRODUCTION HOLD.
Baseline: `3e5ecac3bd4c911f440320ebc33f9a231d8805a9`.

The next 92LH qualification cannot safely call `app.py` merely to obtain a
process handle. Its `main()` calls `load_env_file`, module wiring,
`ensure_assets`, database status, `migrate_runtime_files`, pending migrations,
and three background-worker starters before constructing the loopback HTTP
server. `ensure_assets` can create directories and a placeholder asset;
`migrate_runtime_files` can move legacy JSON; pending migrations can update
the database. The daily-social-stats worker starts unconditionally; the
comment and metrics workers depend on runtime settings. This is ordinary
application startup, not an inert identity probe.

The 92LR kernel observation verifies PID, creation time, and liveness only
after a caller supplies a launch receipt. It cannot prove the caller created
the process, that `app.py` and its Python import/dependency closure were
approved, or that startup did not mutate state. `app.py` imports local
modules, changes `sys.path` and environment, and can load optional Python
packages; a hash of `python.exe` or `app.py` alone is insufficient.

Next qualification needs a reviewed, side-effect-bounded app launch package
and an independently trusted creator retaining its own returned process
handle. The reviewed launch contract must identify the exact source/runtime
closure, environment, state roots, worker policy, timeout, one-attempt budget,
and cleanup/reconciliation before any native app or protected-pipe test.
An inert fixture may validate native handle mechanics but must not be
reported as the real app-instance proof. No app, Kilo/OpenCode receiver,
model, Docker mutation, GPU, ComfyUI, or production activation occurred.
