# EA-4E.71 - Owned Pipe and Worker Process Qualification

Baseline: a24e4b12105f261ef3e9ecab0343a7f19d0842a3.

Historical EA-4E.70 HOLD is retained: two constructor calls denied before child launch by unidentified stdin descriptor writes. No passing child proof was obtained in that invocation.

Correction: a new test-owned OwnedPipeScope permits only open of the active Popen constructor's p2cwrite descriptor, in the same thread, with the frozen command, stdin=PIPE, write-only mode and exact constructor code identity. Scope exits on exceptions and prohibits nesting. Other descriptors, file paths, modes, commands, call sites, threads and escaped scopes remain denied. Thirteen dedicated fake tests plus predecessor safety gate: 89 passed, zero process/filesystem tripwire events.

The separate two-probe process guard wraps the existing filesystem path validator only during its test envelope, forwarding every unqualified access to the original deny rule. Existing filesystem/fake-only guard source files are unchanged. Scope source canonical LF hash is 0b00b4041498d5a39e99e685341ba2359807ba3f3383839f5f31e0ffb357b3ca. Installed subprocess.py exact-byte hash is 85d29b2bf0249f5436838298c9a60ee93508b1102e9ac43b001f8a7e7ae8f375. Launcher, entrypoint, admission and containment canonical source pins plus interpreter/worker exact-byte pins remain mandatory.

Working bounded qualification: 2 passed; exactly two creation attempts, two qualified stdin pipe opens, zero prohibited events, zero filesystem violations, zero owned children alive. One real deterministic worker persists STARTED and returns its acknowledgement; the second exceeds communication timeout and is terminated/reaped with pipes closed. Session-final cleanup covers both returned handles.

Candidate closure: tools/ea4e70_worker_process_guard.py, tests/hermes_core/test_ea4e70_worker_process_qualification.py, original EA-4E.70 HOLD evidence, tools/ea4e71_owned_pipe_scope.py, tests/hermes_core/test_ea4e71_owned_pipe_scope.py, this evidence. Dependencies in the committed tree: tools/ea4e67y_worker_admission.py, tools/ea4e67z_worker_containment.py, tools/ea4e68_worker_entrypoint.py, tools/ea4e69_worker_launcher.py, tests/hermes_core/fixtures/local_worker_stub.py, tools/ea4e67m_filesystem_guard.py, tools/ea4e67n_nonlive_report_host.py and tools/ea4e67_fake_only_guard.py. These test-only guards are acceptance-owned, not production authority. Full staged/committed-tree exports reconstruct this dependency surface without protected successor WIP.

Checkpoint gates: repeat both 89-test fake-only gate and exact two-probe qualification against staged-only and committed exports, each with fresh basetemp. Normal push only if fresh remote baseline still equals the governing parent. Do not stage protected successor WIP.

Limits: no receiver, agent, model, production activation, network, GPU or ComfyUI workload. Python auditing is not universal native-syscall isolation. Child network/out-of-root denial has not been deliberately exercised, original adapter/coordinator fault matrix and crash/replay durability are not qualified by these two probes, and full successor regression remains required. Production readiness remains unproven.
