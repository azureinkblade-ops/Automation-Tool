# EA-4E.73 - Original Worker/Coordinator Matrix Qualification

Baseline: 3eba7340469aa54d7fb667c7b327259c5599031f.

Scope: three new acceptance-owned files: tools/ea4e73_worker_matrix_guard.py, tests/hermes_core/test_ea4e73_missing_executable_admission.py, this evidence. Original production process control, adapter/coordinator implementations, original test files, and existing guard sources are unchanged. Protected successor WIP is excluded.

The guard installs before collection, so production default popen factories capture the guarded callable. It validates the original canonical argv/node, exact interpreter/helper pins, bootstrap source/runtime pins, environment/cwd/options, per-node budgets and aggregate 14-attempt ceiling. Only then does it wrap the argv through the qualified child entrypoint, preserving the original Windows CREATE_NO_WINDOW and text/pipe options. Creation stays synchronous; production communication, timeout, reconciliation and cleanup logic remain exercised.

The exact missing executable C:/does/not/exist/python.exe is checked absent and admitted only in two original nodes with their exact helper/argv shape. FileNotFoundError is raised without invoking a constructor, so production ProcessSpawnError/PROCESS_CREATION_FAILED behavior is tested. Each non-launch case has a separate one-attempt ceiling. This does not grant arbitrary executable authority or fake a success result.

Eight new fake tests plus predecessor gate: 109 passed, zero fake-only/filesystem violations. Working original matrix: 18 passed; 14 worker creation attempts, two qualified missing-executable non-launches, 14 qualified stdin pipe opens, zero prohibited events, zero filesystem violations, zero owned children alive.

Original tests cover valid acknowledgement, definitive rejection, committed acceptance recovery after missing/malformed acknowledgement, pre-acceptance ambiguity, bounded acknowledgement and SQLite lookup timeouts, synchronous creation semantics, one logical replay row, authoritative lookup, dry-run safety, default fake coordinator and explicit coordinator lineage/reconciliation without EXECUTING projection. No assertions were skipped or weakened.

Temporary fixture-tree removal calls are retained inside basetemp by the test envelope; stores are still closed and every returned process handle is reaped. Removal outside basetemp is denied. No repository or fixture files are deleted.

Reconstructible closure: complete staged/committed exports include original tests and their canonical test_execution_launch_admission helpers; all tools/hermes_core production dependencies; admission, child containment, guarded entrypoint, bootstrap verifier, owned-pipe scope, runtime/source verifier and frozen deterministic helper; fake-only/filesystem/report-host guards. Runtime interpreter and installed subprocess.py are external hash-pinned dependencies. All new guard/tests/evidence are acceptance-owned, not production authority.

Acceptance: repeat 109-test fake-only ladder and unchanged 18-test original matrix against staged-only and actual committed exports with fresh basetemp. Each matrix invocation has a 14-attempt ceiling; three independent verification invocations use 42 worker creations and six non-launch checks in total. Normal push only against unchanged governing remote parent.

Remaining: frozen OpenCode pipe workload qualification, unavailable historical capture/runtime dependencies, fresh complete successor regression and separately governed production/live-agent readiness. No receiver/model/production activation/network/GPU/ComfyUI workload was performed. This matrix does not establish universal native-syscall isolation or production readiness.
