# EA-4E.72 - Installed Child Policy Qualification

Baseline: fdb25f998711139c22e3b1666f600e3f5ecf32f0.

Scope: five new test-owned files: tools/ea4e72_child_policy_probe.py, tools/ea4e72_child_probe_guard.py, tests/hermes_core/test_ea4e72_child_policy_probe.py, tests/hermes_core/test_ea4e72_probe_admission.py, this evidence. Existing production code, guard sources and protected WIP are unchanged.

Authority: one named dedicated test, one child creation attempt per explicit qualification invocation. Exact interpreter pin, canonical LF probe/helper dependency pins, installed subprocess.py exact-byte pin, credential-free environment, isolated nested child root and original owned-stdin scope remain enforced. Any other node, budget, command, executable/helper, flags, shell, pipe, environment or cwd fails admission. Twelve fake admission tests plus predecessor gate: 101 passed, zero fake-only/filesystem events.

The real child installs the existing Python audit policy before loading JSON/SQLite workload logic. It emits socket.connect, subprocess.Popen and os.system audit events directly, all denied by the installed hook. No socket connection, shell command or nested process call is made. These are real child-hook event-denial proofs, not evidence that native syscalls or every API route are sandboxed.

Actual file and SQLite escape attempts target sibling paths inside disposable parent test storage but outside the narrower child root. Both are denied; parent verifies neither escaped file exists. Writes and SQLite CREATE/COMMIT inside the child root succeed. Owned cleanup reaps the sole child and closes pipes.

Working gate: 1 passed, exactly one creation attempt, one qualified stdin pipe open, zero prohibited parent events, zero filesystem violations, zero owned children alive. Repeat 101-test fake-only gate and one-child proof in staged-only and committed exports with fresh basetemp before normal push. Total successful child creations for the three independent verification runs will be three, not one across the checkpoint.

Dependency closure in committed exports: admission, child containment, bootstrap-source verifier, owned-pipe scope, filesystem/fake-only guards and report-host plugin from EA-4E.67Y through 71; frozen interpreter and installed subprocess.py are external runtime dependencies explicitly hash-pinned. Guards/probe/tests are acceptance-owned, not production authority. No untracked protected successor dependency is required.

Remaining: original adapter/coordinator fault matrix, replay/crash semantics, fresh complete successor regression and exact separately governed activation/live-agent readiness. No receiver/model/production activation/GPU/ComfyUI activity was performed. This checkpoint alone is not production readiness.
