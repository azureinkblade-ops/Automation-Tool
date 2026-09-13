# EA-4E.90 Durability Evidence Retention Qualification

Governing parent: 5d7f7a984400f59ee39617469de98479d3c021ac.
Scope: one test-owned wrapper, one focused test file, this evidence.
Production code and frozen EA67J process admission/helper bytes are unchanged.

The wrapper delegates admission, terminal accounting and process cleanup to
tools/ea4e67j_durability_process_guard.py. Its exact six-node restriction,
interpreter/helper hashes, fourteen-launch ceiling, credential-free environment
and parent/child network/nested-process denials remain in force. It retains
shutil.rmtree calls only within the fresh basetemp and its dedicated sibling
helper root; outside paths and descriptor-relative cleanup are denied.

The frozen guard creates the fresh basetemp before pytest requests tmp_path.
The wrapper binds pytest's internal _tmp_path_factory._basetemp at session start
to that created root, preventing pytest from deleting and recreating it.
This is a test-runtime private API dependency, covered by a focused test and
the actual six-node integration run; requalify when pytest changes.

Working results: 18 focused/frozen-guard tests passed, zero fake/filesystem
tripwire events. Six original OS durability nodes passed with fourteen helper
launches, zero denials, and three temporary-directory trees retained.
Two earlier process configurations each passed three historical nodes and
errored during setup of three tmp_path nodes, with five launches and zero
process denials. Diagnostics identified pytest's extended-length Windows
cleanup path. No files were deleted; failed-run evidence remains retained.

Independent staged source tree: 79c1446012ee9b4dc6c217e246bf11007b039d51.
Tracked tools/tests/.gitattributes exported to .ea4e90-index-a.
Staged results: 18 focused tests passed with zero fake/filesystem events;
six original process nodes passed, fourteen launches, zero denials, three trees
retained. The evidence file is added after this source-only staged verification.

Process command uses the pinned .venv-stage2-v2 interpreter and:
`-m pytest -q -p no:cacheprovider -p tools.ea4e90_durability_retention_guard
-p tools.ea4e67n_nonlive_report_host --basetemp=<fresh path> --tb=short`
followed by exactly these nodes:

```text
tests/hermes_core/test_ea4e33_operational_safety.py::test_multi_process_claim_tested
tests/hermes_core/test_ea4e33_operational_safety.py::test_os_process_precommit_crash_tested
tests/hermes_core/test_ea4e33_operational_safety.py::test_os_process_postcommit_crash_tested
tests/hermes_core/test_ea4e33a_store_rollback_detection.py::test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent
tests/hermes_core/test_ea4e67k_process_durability.py::test_abrupt_postcommit_crash_keeps_consumption_and_fails_closed
tests/hermes_core/test_ea4e67k_process_durability.py::test_simultaneous_claims_have_one_winner_and_three_clean_denials
```

Focused command uses no cacheprovider, fake-only/filesystem/report-host plugins,
a fresh basetemp and these files: test_ea4e90_durability_retention.py and
test_ea4e67j_process_guard.py under tests/hermes_core.
Do not compose the blanket fake-only process replacement with the independently
bounded process envelope. The process envelope has parent network/shell denies
and child audit hooks, not a universal native-syscall sandbox or the broader
filesystem audit used by the focused fake gate.

Post-commit repeat of both gates is required before checkpoint acceptance.
No assertion was weakened. Historical postcommit recovery testing is distinct
from the stronger EA67K abrupt os._exit test; both remain tested as written.
Missing genuine OpenCode historical capture remains unresolved. Broad EA88 raw
failures are not relabeled full green. No receiver task/model, production
activation, GPU or ComfyUI work was performed. No file deletion authorized.
