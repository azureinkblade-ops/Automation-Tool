# EA-4E.67Y Worker Admission: Non-Live

Baseline: 75195f85913ec46c28f189c188d7d3241c05f367.
Scope: test-owned admission validator, dedicated tests, targeted attributes,
and this evidence. No production semantics or existing guards changed.

validate_worker_launch validates only; it returns a temporary registry path.
It never launches, updates counters, issues authorization or invokes a receiver.
It freezes 13 launch-capable node IDs, per-node fault flags, one launch each
except replay's conservative two, aggregate ceiling 14. This is an admission
ceiling, not a verified executed count. Five of the collected 18 nodes do not
receive launch admission, including missing-executable paths. Those need their
own prelaunch failure fixture, not permission for arbitrary executable paths.

Executable/helper exact paths and SHA256 are checked on each validation.
State must be absolute under explicit existing isolated basetemp, with SQLite
suffix and no traversal/alternate stream. Environment excludes credentials,
system variables must match ambient OS values, TEMP/TMP stay within basetemp.
Counter data must contain only known nodes and nonnegative bounded integers.
Budget exhaustion, unknown node, extra argv, wrong executable/helper, identity
drift, unsafe cwd/state/environment all reject before launch.

Initial export failed 1 test (42 passed) because adding the LF attribute
normalized helper bytes. The helper is now explicitly mechanically normalized
to LF without semantic changes; its frozen SHA256 is
622547fb220f7cb1069aea7580b71321b22132cc480e3b410e2a0910e418eff0.
Git confirmed the helper blob was already LF: normalization changes checkout
bytes only, not the committed helper. Final commit has four files, no helper
blob delta. The old observed hash is historical. Final staged and committed
exports both passed 43 tests with zero process/filesystem events.
Focused admission tests: 15 passed. Expanded admission and process/filesystem/
reporting safety gate: 43 passed, zero guard events. Command uses python -m
pytest -q -p no:cacheprovider -p tools.ea4e67_fake_only_guard
-p tools.ea4e67m_filesystem_guard -p tools.ea4e67n_nonlive_report_host
--basetemp=.pytest-ea4e67y-final-a with test_ea4e67y_worker_admission.py,
test_ea4e67m_filesystem_isolation.py, test_ea4e67n_nonlive_report_host.py,
test_ea4e67j_process_guard.py and --tb=short. Independent source gates required.

ADMISSION_VALIDATION=IMPLEMENTED_NONLIVE
CHILD_CONTAINMENT=NOT_IMPLEMENTED
OWNED_CHILD_CLEANUP=NOT_QUALIFIED
LAUNCH_EXCEPTION=NOT_ENABLED
PRODUCTION_READY=NO

Next: child-side containment and owned-process shutdown, negative qualification,
then exact bounded helper gate. Python-level guards are not universal OS
sandboxing. No real receiver/model/GPU/ComfyUI, restart, deployment or file
deletion. Missing historical replay and binary identities remain open.
Successor WIP remains excluded; broad successor HOLD remains unchanged.
