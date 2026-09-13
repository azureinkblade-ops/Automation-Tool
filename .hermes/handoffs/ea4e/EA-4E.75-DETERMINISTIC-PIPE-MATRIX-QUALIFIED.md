# EA-4E.75 - Deterministic Pipe Matrix Qualification

Baseline: 683984d5236a2d45bc7a06030e13c00e22b8df82.

Scope: three new acceptance-owned files: tools/ea4e75_pipe_matrix_guard.py, tests/hermes_core/test_ea4e75_pipe_admission.py, this evidence. Original OpenCode production code, original test assertions and existing guard sources remain unchanged; protected successor WIP is excluded.

Authority: exactly the 15 frozen original real-Python pipe nodes, one creation attempt each, 15 total per explicit invocation. Parent guard is installed before collection, so captured default Popen factories remain governed. Exact original -c snippet or malformed fixture bytes are validated but never executed; only the fixed enumerated helper receives process authority. Helper/inventory/child policy dependencies and interpreter/subprocess runtime identities are pinned. No installed OpenCode, model, shell, network, production activation, GPU or ComfyUI workload occurs.

Original stdin=DEVNULL, binary stdout/stderr PIPE, cwd, Windows CREATE_NO_WINDOW and production reader/drain/retention logic are preserved. Original empty test environment is replaced only at the qualification launch boundary with SYSTEMROOT/SYSTEMDRIVE plus TEMP/TMP bound to that child's isolated root; no credentials are inherited. Child policy is installed before helper workload logic. No descriptor-write exemption is required for DEVNULL/read-only parent pipes.

Independent registration retains original process handles, even when reader-failure tests deliberately replace adapter process references with mocks. Tracking wrapper records actual reader threads without changing start results. Final cleanup reaps all handles and joins readers through Thread class methods, bypassing only deliberate instance-method mocks for cleanup verification. Any leaked child/reader, unexpected call or incomplete count fails qualification.

Eight new fake admission tests plus predecessor ladder: 155 passed; zero fake-only/filesystem events. Working pipe matrix: all 15 original tests passed, 15 helper creation attempts, zero prohibited events, zero filesystem violations, zero live owned children/readers.

Coverage: stdout/stderr/dual capture, large output without deadlock, distinguishable empty output, timeout termination, stdout/stderr/dual overflow retention, stuck/error reader propagation, successful reader finalization, absence of synthetic truncation markers, malformed JSONL and cancellation ownership. The separate fake-only stdin test is not a real process workload and is not selected in this matrix.

Declared closure: original test_opencode_adapter.py and tools/hermes_core production dependencies; prior exact pipe inventory/helper, admission/interpreter pin, child containment, bootstrap-source/runtime verifier and its source dependencies, fake-only/filesystem/report-host guards. All new guards/tests/evidence are acceptance-owned. Full staged/committed exports reconstruct this closure without protected untracked successor dependencies.

Acceptance: repeat 155-test fake-only ladder and the exact 15-test original pipe matrix against staged-only and committed exports, fresh basetemp each invocation. Three independent matrix proofs use 45 successful helper creations total, not 15 across the checkpoint. Normal push only if fresh remote baseline still equals the governing parent.

Remaining: fresh complete successor regression with distinct bounded workload gates, missing historical capture/runtime evidence and separately governed production/live-agent readiness. This proves deterministic pipe mechanics, not installed OpenCode compatibility, universal native-syscall containment or full production readiness.
