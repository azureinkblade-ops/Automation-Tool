# EA-4E.67U Upper-Layer Single-Binding Fixtures

Baseline: efd2432dda0acf00f7b26834926380ebbdb38a99.
Scope: EA-4E.38, 39, 41 test modules and this evidence only.

Nine receiver-mutation fixtures unnecessarily created two simultaneous
bindings. Each now binds only the originating authorization receiver and
asserts active count one and absent target binding. Both fake executors remain
registered. Original explicit mutation rejection reasons remain unchanged:
APP_TO_CALLER_RECEIVER_MUTATION, REAL_CALLSITE_TO_ADAPTER_RECEIVER_MUTATION,
USER_ACTION_TO_CALLSITE_RECEIVER_MUTATION. Existing next-layer/zero-executor
checks remain. These layers reject mismatch before the next layer is invoked;
there is no need to bind the target or fake production lookup behavior.

Candidate gate: complete EA-4E.38, 39, 41, 37, 36 modules plus filesystem
isolation, reporting and process-guard modules: 134 passed, zero process
and filesystem tripwire events.

Command: python -m pytest -q -p no:cacheprovider
-p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard
-p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e67u-gate-a
with those eight modules and --tb=short. Independent staged-only and actual
committed exports must pass before push. No successor WIP included.

No production or guard changes, real receiver/model invocation, authorization
ceremony, GPU/ComfyUI, deployment, restart or file deletion occurred.
Broader successor HOLD remains; feature-gate/cross-runtime binding fixtures,
real-process partition, and missing binary/replay dependencies remain open.
