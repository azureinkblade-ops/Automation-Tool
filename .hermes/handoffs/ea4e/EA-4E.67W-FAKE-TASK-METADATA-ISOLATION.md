# EA-4E.67W Fake Task Metadata Isolation

Baseline: f4b8d4b1721b28cf61f974506dfc6e656e0832a1.
Scope: OpenCode adapter test module and this evidence only.

67Q recorded 36 blocked Popen attempts. Source/report inventory separates:
- 7 fake task shaping/transport checks accidentally resolving default binary
  metadata (TaskDelivery six nodes and ReceiverContractTruth one node).
- 2 genuine coordinator process probes.
- 12 genuine local worker process tests (RealSpawn, TimeoutMechanics, Replay).
- 15 genuine OpenCode Python pipe/capture/overflow/finalization/cancellation
  process tests. Passing OS nodes are not exhaustively inventoried by the
  failure report; 29 is a blocked-node count, not total OS-test inventory.

The fake_task_runtime fixture supplies the existing temporary trusted config
and injected version probe only to TaskDelivery and ReceiverContractTruth.
Pytest restores collaborators afterward; genuine process tests are unchanged.
Real task validation, argv construction, runtime metadata checks against the
test-owned binary bytes and temporary registry persistence remain. Fake tests
do not prove installed binary compatibility or real pipe behavior.

Candidate gate: those two classes, TrustedConfig class, filesystem isolation,
report host and process guard suites: 46 passed, zero guard events.
Command uses python -m pytest -q -p no:cacheprovider
-p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard
-p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e67w-gate-a
with the above nodes/modules and --tb=short. Independently verify staged-only
and actual committed exports before push.

No tests skipped, deselected or marked passed by this change. Broad 67Q HOLD
and all genuine OS obligations remain visible. No launch exception granted.
Next process qualification requires a separately bounded helper/executable
identity, exact argv/environment, owned-child cleanup, budget and audit
envelope; do not simply permit arbitrary Python or installed receiver launches.
Missing binary and live-spool replay dependencies remain separate open work.

No production/guard changes, live receiver/model, authority issuance ceremony,
GPU/ComfyUI, deployment, restart or file deletion. Successor WIP excluded.
