# EA-4E.84 Committed Broad Regression

Source: 900d922541a094ed512b03ca1c68eb3d86262e7b, complete git archive, no protected WIP/untracked successor candidate imported.
Disposition: BROAD REGRESSION RED / FAILURE INVENTORY VERIFIED / PRODUCTION READINESS HOLD.

Initial narrow export run: 11 collection errors because app.py was omitted; targeted reproduction confirmed ModuleNotFoundError: app. This is an export defect, not regression acceptance. Retained result .pytest-ea4e84-broad-a in ea4e83-commit. Corrected by full archive of exact committed source; no existing files deleted or modified to mask errors.

Complete export run: 3372 passed, 61 failed, 6 explicitly deselected OS durability nodes, 104 subtests passed, one SyntaxWarning in app.py for invalid escape sequence. Exit 1. Filesystem tripwire events 0, fake-only Popen attempts denied 34; no metadata/task processes admitted in this broad fake-only gate.

Failure partition from final JUnit case names/messages:
- 34 restricted process-boundary cases: 2 original Codex metadata nodes; 2 EA70 worker probes; 1 EA72 child-policy probe; 2 coordinator probes; 12 original worker process cases; 15 original OpenCode pipe cases. Separate bounded qualification evidence exists, but this raw gate remains failed, not normalized to green.
- 25 Kilo cases depend on absent pinned 7.5.16 executable: EA64B identity 1; Kilo adapter/config/process classification 14; Kilo invocation/accounting/precheck 5; production fake-activation 5. Final messages consistently show missing executable. Committed source does not contain protected successor WIP, unlike EA76 mixed working-tree run; historical counts therefore are not directly interchangeable.
- 1 missing genuine OpenCode stdout JSONL capture: run-d1eca109.stdout.jsonl. Not fabricated or replaced.
- 1 export-context fixture: RuntimeNamespaceTests.test_live_harness_head_is_valid_source_binding reads .git/HEAD, absent by definition in git archive. This requires explicit source-binding qualification or a Git-bearing committed checkout; no fake HEAD file created.

JUnit: ea4e84-full-commit/.pytest-ea4e84-broad-b/result.xml. SHA-256 7b2e530d0fadb7f45e53591e1c9ef14f3d10dcf382efe6cc440f60e0e5b5152e.
Command: python -m pytest -q -p no:cacheprovider -p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard -p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e84-broad-b --junitxml=.pytest-ea4e84-broad-b/result.xml tests/hermes_core/ --tb=no; -k excludes exactly test_multi_process_claim_tested, test_os_process_precommit_crash_tested, test_os_process_postcommit_crash_tested, test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent, test_abrupt_postcommit_crash_keeps_consumption_and_fails_closed, test_simultaneous_claims_have_one_winner_and_three_clean_denials.

Next: review/qualify the protected Kilo successor closure rather than assuming it can ship; qualify Git-dependent source binding against actual committed Git context; recover genuine replay evidence or retain missing-provenance failure. No production/test edits in this checkpoint. No broad all-green or zero-new-regressions assertion. No real receiver/model/activation/GPU/ComfyUI; protected WIP preserved, no deletion.
