# EA-4E.91 Committed Regression and Capture Recovery Boundary

Source: synchronized commit 808c7bf87da3793a7da26f99d766711e829f7fd7.
Detached Git checkout: .worktrees/ea4e91-committed-qualification.
Tracked checkout status remained empty after qualification.

## Complete fake-only result

3408 passed; 35 failed; six deselected; 104 passing subtests; one warning.
Elapsed: 120.04 seconds. Exit status: 1. No full-green claim.
Filesystem tripwire events: 0. Fake-only process tripwire events: 34, all denied.
The existing app.py invalid escape sequence warning remains unchanged.

Structured JUnit comparison against EA88: 35 old failed nodes, 35 current failed
nodes, new nodes [], resolved nodes []. Four new retention tests pass.
The 34 process-boundary tests retain their raw failures in this blanket gate;
EA89 separately requalified those cases under exact bounded process envelopes.
The six excluded OS durability nodes were separately requalified in EA90 from
working, staged and committed exports, with fourteen frozen helper launches,
zero denials and temporary-directory evidence retained. These separate results
do not erase the raw broad failures or establish live production readiness.

JUnit path: .pytest-ea4e91-broad-a/result.xml in the detached checkout.
SHA-256: 04e3d7e535f673dd44ec8d4652c7a3383492d25495add4e6d74d6320edae9966.

Command: pinned .venv-stage2-v2/Scripts/python.exe, `-m pytest -q
-p no:cacheprovider -p tools.ea4e67_fake_only_guard
-p tools.ea4e67m_filesystem_guard -p tools.ea4e67n_nonlive_report_host
--basetemp=.pytest-ea4e91-broad-a
--junitxml=.pytest-ea4e91-broad-a/result.xml tests/hermes_core/ --tb=no`.
The `-k` expression excludes exactly the six named OS nodes recorded by EA90:
test_multi_process_claim_tested, test_os_process_precommit_crash_tested,
test_os_process_postcommit_crash_tested,
test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent,
test_abrupt_postcommit_crash_keeps_consumption_and_fails_closed,
test_simultaneous_claims_have_one_winner_and_three_clean_denials.

## Genuine capture recovery search

Missing expected capture remains:
C:/Users/David/AppData/Local/Hermes/runtime/ea4e/opencode/spool/run-d1eca109.stdout.jsonl.
Filename search of Local/Hermes and Hermes Vault found two alternate stdout
JSONL files under node/node_modules/opencode-ai/bin/test_spool:
run-e33c6795.stdout.jsonl and run-2d9a92ca.stdout.jsonl. Both are zero bytes and
cannot provide parser replay evidence. They were not replaced or modified.

The initial filename search reported access denied for wisdom,
pending_messages and logs/process-results. An approved read-only recursive
filename/length search of process-results completed with no matching run ID or
JSONL. Wisdom and pending_messages were not opened; this is not an exhaustive
all-backups absence claim. Repository handoff search found normalized EA4 text
and later absence records, not the genuine original payload.

Historical EA4 success remains historical evidence, not reconstructed raw data.
Do not fabricate JSONL, substitute empty or unrelated captures, suppress the
failure, or silently move the test into an expected-failure bucket.

## Next decision boundary

Safe continuation can recover a genuine capture from an identified backup and
validate its provenance before replay. Otherwise, a reviewed test-contract
decision must explicitly separate portable synthetic parser coverage from an
unavailable historical replay dependency, leaving the missing historical proof
visible. A new live capture would be new evidence, never recovery of EA4, and
requires an exact one-shot receiver/model authorization and accounting packet.
This checkpoint authorizes none of those live operations.

No production/test code changed in EA91. No files deleted, receiver task/model
invoked, production activated, GPU generation or ComfyUI call performed.
Evidence-only checkpoint; normal push requires its exact reviewed commit.
