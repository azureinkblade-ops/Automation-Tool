# EA-4E.67R Fake OpenCode Durable Store Fixture

Baseline: 223b85ed14a802daa7e6a407d6ffcf984bd8619f.
Scope: test_opencode_invocation_authorized_live.py and this evidence only.

The legacy fake qualification supplied an unpersisted synthetic authorization
to a policy without a durable store. Production correctly rejected claims with
DURABLE_INVOCATION_AUTHORIZATION_STORE_REQUIRED. No production remediation is
needed for this demonstrated failure.

The autouse fixture now creates a tmp_path SQLite store and integrity anchor.
Test-only constructor collaborators persist synthetic authorizations and supply
the real store-backed policy. Validation, atomic claim, consumption, and second
claim denial remain real production behavior, not mocked decisions. Teardown
checks persisted consumption whenever the fake executor was called. Existing
real executor, adapter, and process tripwires remain intact.

Candidate results under unchanged process/filesystem/report guards:
- Legacy module: 36 passed, zero process and filesystem events.
- Legacy module plus OpenCode 25A, filesystem isolation, report host, process
  guard suites: 80 passed, zero process and filesystem events.
Fresh explicit basetemp was used for each run. No live receiver/model,
authorization issuance ceremony, server restart, GPU, or ComfyUI work occurred.
Synthetic fake outcome counters remain simulated evidence, not real invocation
accounting. No guard or durable-store requirement was weakened.

The 67Q broad result remains historical HOLD: 3217 passed / 73 failed / 0
errors / 104 passing subtests / 6 deselected, with 36 blocked process attempts.
This slice does not qualify the complete successor chain. Real-process tests,
binding-limit fixtures, missing binary/replay dependencies remain separate.
All successor WIP is excluded from this checkpoint.

Independent final gate command uses python -m pytest -q -p no:cacheprovider,
-p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard
-p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e67r-export-a
--junitxml=.pytest-ea4e67r-export-a/result.xml, the five modules listed above,
and --tb=short. Verify the staged-only and actual committed exports before push.
