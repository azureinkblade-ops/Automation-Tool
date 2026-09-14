# EA-4E.92S Parser Source Extraction - Partial Qualification

Date: 2026-09-14
Baseline: fca9e3bd09eb8c9c9cc3105c4c9161bd248b5aaa
Status: SOURCE EXTRACTION TARGETED PASS / UNCOMMITTED WIP
Overall EA92S: FREEZE HOLD / PARSER EXECUTION NOT QUALIFIED

## Scope

New test-owned, capability-free helper:
`tools/ea4e92s_parser_source.py`.
Synthetic fixtures:
`tests/hermes_core/test_ea4e92s_parser_source.py`.
This evidence is the third candidate file. No production integration changed.

The helper accepts caller-supplied immutable bytes only. It checks exact parent
length/hash, unique ordered markers, exact region offset/length/hash and strict
UTF-8 before returning inert bytes. It neither reads/writes files nor loads,
adapts or executes JavaScript. Constants are pinned to the observed local
Playwright bundle, not fixture identities.

Parent SHA256: 01511e45db7646e2a12890de8d7866caa0754c8799db6407a6345236f4bed0c4
Parent bytes: 2901663
Region offset: 545346
Region bytes: 570486
Region SHA256: d5c94f357a5098056ec075c1cf91bb487f99e7becb5e6448c3f9415de159097c

## Verification

Interpreter: `C:\Users\David\Documents\Automation tool\.venv-stage2-v2\Scripts\python.exe`.

Final targeted command:
```text
python -m pytest -q -p no:cacheprovider -p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard -p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e92s-source-b tests/hermes_core/test_ea4e92s_parser_source.py tests/hermes_core/test_ea4e92p_static_binary_inspection.py
```

16 synthetic extractor cases + 18 predecessor cases = 34 passed / 0 failed.
Process/network tripwire events: 0. Filesystem tripwire events: 0.
Initial extractor-only run: 12 passed before four additional boundary cases.

An independent read-only Python invocation supplied the installed bundle bytes
to the helper. Returned length/hash matched the pinned region above. This
invocation was outside pytest tripwires; it loaded only the Python extractor,
read the explicit bundle path and printed length/hash. No JS was evaluated or
extracted file written.

Synthetic tests temporarily pin synthetic constants through pytest monkeypatch;
those results must not be represented as real parser behavioral qualification.

## Remaining Boundary

Existing fake-only guard denies process creation and network connection at the
Python level. It explicitly is not an OS sandbox. A scoped search of tools and
tests/hermes_core found no JobObject/AppContainer/restricted-token or process
memory-limit implementation using the searched spellings; this is not a claim
of machine-wide absence.

Parser initialization review, derived artifact/license identity, Node version,
OS containment, timeout/memory enforcement and actual parser fixtures remain
OPEN. No inspection bound increased and no SDK/receiver/model/browser/GPU or
ComfyUI execution occurred. No authorization or activation issued.

Full regression, staged-tree qualification and committed-tree qualification
had NOT run at the initial targeted checkpoint. See subsequent working-tree
regression below. No full-green or production readiness claim.
No staging, commit or push performed. Retain candidate WIP and unrelated files.

## Subsequent Working-Tree Full Fake-Only Regression

Ran the full `tests/hermes_core/` gate on the integration working tree using the
same three guard/report plugins above, `--tb=no`, fresh basetemp
`.pytest-ea4e92s-full-a` and `--junitxml=.pytest-ea4e92s-full-a/result.xml`.
The inherited six separately governed OS-test exclusions were unchanged:
```text
-k 'not test_multi_process_claim_tested and not test_os_process_precommit_crash_tested and not test_os_process_postcommit_crash_tested and not test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent and not test_abrupt_postcommit_crash_keeps_consumption_and_fails_closed and not test_simultaneous_claims_have_one_winner_and_three_clean_denials'
```

Result: 3629 passed / 35 raw failed / 6 deselected / 104 subtests passed.
Duration: 134.58 seconds. Exit status: 1.
Filesystem tripwire events: 0. Process tripwire events: 34 denied Popen attempts.
Do not describe this full run as zero tripwire events or fully green.

Compared sorted `classname::name` failure identities with retained committed
EA92P report `.pytest-ea4e92p-committed-a/result.xml` in the
`ea4e92p-committed-qualification` checkout. Baseline failures: 35; current: 35;
added: 0; resolved: 0. The comparison completed without read errors.
Classification: NO NEW WORKING-TREE REGRESSIONS / INHERITED FAILURES VISIBLE.

Current report SHA256:
`257c6a903fb7565fed563f27afdda1d6755af5d88405b2d8b6d2b92751ee27c5`.
Tracked working-tree diff was empty at gate start; only the three new candidate
files are part of this change. The working-tree gate is not a clean-export or
committed-tree qualification. Staged/committed gates remain unrun.
No staging, commit, push, parser/SDK execution, activation or receiver/model
invocation performed. Parser containment and semantic qualification remain OPEN.

## Subsequent Fake Lifecycle Interface

Added test-owned tools/ea4e92s_containment_lifecycle.py and
tests/hermes_core/test_ea4e92s_containment_lifecycle.py. No native backend supplied.
19 scripted lifecycle + 16 extractor + 18 static predecessor cases passed:
53 passed / 0 failed, both tripwire event counts zero, 0.22s.
Fresh test root: .pytest-ea4e92s-lifecycle-b; same guard/report plugins and pinned
Python as above. The first run had 51 passed / 3 setup errors caused by a 4 MiB
pytest parameter ID; explicit short IDs fixed the fixture, assertions unchanged.

CAPTURED_UNVALIDATED output is not parser proof. UNKNOWN cleanup or creation
outcomes require caller reconciliation before any subsequent launch. Native
process/network/filesystem/resource enforcement is not implemented or qualified.
The earlier working-tree full gate predates this interface; rerun is required.
Five candidate repository files now comprise the uncommitted WIP, including this
evidence. No staging/commit/push or actual parser/SDK/receiver execution occurred.

## Lifecycle-Inclusive Working-Tree Full Gate

Full Hermes Core rerun used the same pinned Python, guard/report plugins,
six OS-test exclusions and --tb=no as the prior full gate, with fresh basetemp
.pytest-ea4e92s-full-b and JUnit .pytest-ea4e92s-full-b/result.xml.

Result: 3648 passed / 35 raw failed / 6 deselected / 104 subtests passed.
Exit 1; duration 113.56 seconds. Process tripwire: 34 denied Popen attempts;
filesystem tripwire: 0. No new failure identities against committed EA92P:
baseline 35 / current 35 / added 0 / resolved 0.

Report SHA256:
729b44d906aef29a344d02a20f0c9f1614d253cccbcad6aa403c8f0e2e5abce3

Candidate source/test fingerprints recorded during the gate:
- tools/ea4e92s_parser_source.py: a1465325e2cc1b0442f04b89a0bc0251c012ab06f7436dc2e0477d91572a1aac
- tools/ea4e92s_containment_lifecycle.py: e3da8511a3ff7bc50058b44757ecc7edfca1c5048df88ff124fec1aa6c15849c
- tests/hermes_core/test_ea4e92s_parser_source.py: 8eace3a0c39ecd66f7501184d7d4ce8025c5d57c08a8697e2323dff632e1f631
- tests/hermes_core/test_ea4e92s_containment_lifecycle.py: b547c1ca7c40a1926085f94eb13ff3b553c44cb714dd459ba02310ad3478671a

Tracked-file status was clean during this gate. The five new candidate files
remain uncommitted; no staged/clean-export/committed-tree gate claimed.
Classification: LIFECYCLE-INCLUSIVE WORKING-TREE NO-NEW-REGRESSIONS PASS,
RAW GATE NOT GREEN. Native containment, parser behavior and SDK analysis remain
unqualified. No staging, commit, push or actual receiver/model launch occurred.

## Source Review and Bounded Staged-Tree Qualification

Reviewed exactly the two test-owned helpers, their two fixture files and this
partial evidence. No blocker found for that narrow checkpoint. This is not
approval or qualification of a concrete OS containment backend.

Staged exactly five candidate files; initial index was empty. git diff --cached
--check passed. Initial staged tree 06a813f396ba415fa309bd86c75904c0c25f6cd8
was archived to .ea4e92s-index-a.zip and expanded into new .ea4e92s-index-a,
without untracked files. Bounded gate from the export: 53 passed / 0 failed,
0.14s, process/network and filesystem tripwire counts both zero. Same pinned
Python and guard/report plugins, three targeted test files as above; test root
.pytest-ea4e92s-index-a. Full staged-tree regression was not run.

This evidence update changes only the evidence blob after that initial export;
the final index must be re-exported and the bounded gate repeated before calling
the final staged tree qualified. Record final tree/report identity in the vault
without recursively changing this evidence. No commit or push authorized by this
record. Existing broader 35 raw failures remain visible; no full-green claim.
Native parser/SDK/receiver/model execution remains blocked.
