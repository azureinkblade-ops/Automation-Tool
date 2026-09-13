# EA-4E.86 Committed Successor Broad Qualification

Source d0262d748931628a496a3f3690ef49476f1276f5, retained detached Git worktree ea4e86-committed-qualification, initially zero tracked changes. No WIP imported. Evidence checkpoint parent is the same SHA.
Disposition: KILO FAILURE GROUP RESOLVED / BROAD RED / CLAIM CONCURRENCY INVESTIGATION OPEN.

Full tests/hermes_core gate: 3402 passed, 36 failed, 6 explicitly deselected OS durability nodes, 104 subtests passed, one existing invalid-escape SyntaxWarning in app.py. Exit 1, filesystem tripwire events 0, fake-only subprocess attempts denied 34. Runtime namespace Git-context test passed in real detached checkout; no fake HEAD file.

Final failure list: 34 restricted process-boundary checks as in EA84; missing genuine OpenCode capture 1; TestEA4AClaimConcurrency.test_concurrent_different_claimant_conflict 1. All 25 EA84 missing Kilo binary cases are absent from the final failure list, not inferred from focused qualification. Five dedicated successor cases increase current collection; historical raw totals remain unchanged.

Concurrency failure message: AssertionError: 'conflict' not found in {'ok', 'error'}. At-most-one success is not the complete domain contract: a losing different claimant must receive conflict, never generic error. Entire claim test file isolated on the same committed checkout: 29 passed, zero tripwire events, including its stress cases. That isolation does not exonerate the broad failure or establish inherited/transient classification.

Source trace: _race records error exception type/message, but the failing outcomes assertion does not include that result detail. test_stress_different_claimant checks exactly one success but does not require the loser be conflict, so its passing result cannot prove the failing no-raw-error contract. Next: retain exception diagnostic in assertions and strengthen this existing stress invariant without weakening claim semantics; reproduce against committed source and baseline before narrowly scoped remediation. No EA4A production semantics changed here.

JUnit retained at detached checkout .pytest-ea4e86-broad-a/result.xml, SHA 8ee846e3844c0ff65dde5152ffa579d2e3061e09dcc7902fa405cb57935c3ae5. Broad command same EA84 fake-only/filesystem/report-host gate with fresh basetemp/JUnit; identical six -k OS durability exclusions. Isolation: same plugins, fresh .pytest-ea4e86-concurrency-a, tests/hermes_core/test_execution_authorization_claim.py --tb=short.

No production/test source changed in this checkpoint. No real receiver/model/activation/GPU/ComfyUI, no deletion. Detached checkout/evidence retained. Missing provenance and process qualification partition still open. Production readiness unproven; no full-green/zero-new-regressions claim.
