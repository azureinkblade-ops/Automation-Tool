# EA-4E.67Z Child Policy and Owned Cleanup: Non-Live

Baseline: 7a4015d31f0be370f9615913be012e3a1c3fbaa0.
Scope: test-owned containment module, dedicated tests and this evidence.
No existing production, guard, helper or successor WIP files changed.

child_audit_policy prohibits subprocess/socket/shell/exec/spawn/fork and
ctypes dynamic loading events; permits writes/SQLite only under its resolved
temporary root. It checks both rename/link paths, rejects descriptor writes
and remote SQLite URIs. install_child_guard disables bytecode and installs
the policy, intended only inside the future dedicated child before work imports.
It is not installed in the test runner and is not an OS/native syscall sandbox.

OwnedChildren registers object handles, rejects duplicate registration, and
uses bounded terminate/wait then kill/wait on timeout. Cleanup checks terminal
state, closes owned pipes and attempts every registered child even after errors.
Failures are propagated; no PID enumeration or unrelated process termination.

Focused policy/cleanup/admission gate: 35 passed, zero process/filesystem
events. Dedicated containment suite has 20 tests. No real child was launched.
Direct audit-policy calls and fake handles prove unit behavior only, not
child-side installation or OS reaping. No launch exception enabled.

Expanded gate: these two modules plus filesystem isolation, reporting and
process guard tests. Use python -m pytest -q -p no:cacheprovider
-p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard
-p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e67z-gate-a
and --tb=short. Require independent staged-only and committed export gates.

Next: wire a dedicated frozen child entrypoint and bounded test-only launcher,
prove child policy installation and genuine owned-child cleanup under exact
node/argv/environment/budget envelope. Real receiver/model/activation/GPU work
remains separate. Broad successor HOLD and missing binary/replay remain open.
No production readiness claim, deployment, server restart or file deletion.
