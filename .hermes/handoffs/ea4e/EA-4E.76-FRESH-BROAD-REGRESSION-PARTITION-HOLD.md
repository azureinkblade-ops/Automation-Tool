# EA-4E.76 - Fresh Broad Regression Partition

Status: DIAGNOSTIC EVIDENCE VERIFIED / BROAD READINESS HOLD.
Governing source commit: ce75eaf024b776a8b33d9fddd2049ea0ce5dde6e.
The run includes 13 protected successor WIP files and the existing untracked candidate test; it is not committed-source successor qualification. No production/test/guard changes were made.

Command: stage2-v2 Python -m pytest -q -p no:cacheprovider -p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard -p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e76-full-a --junitxml=.pytest-ea4e76-full-a/result.xml tests/hermes_core/ --tb=no.

The same historical -k exclusions remain explicit: test_multi_process_claim_tested, test_os_process_precommit_crash_tested, test_os_process_postcommit_crash_tested, test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent, test_abrupt_postcommit_crash_keeps_consumption_and_fails_closed, test_simultaneous_claims_have_one_winner_and_three_clean_denials. These six OS durability tests are deselected, not counted as passed.

Completed result: 3384 passed / 36 failed / 0 errors / 6 deselected; 104 subtests passed; 117.60 seconds; exit 1. XML contains 3420 testcase elements, 36 failure elements, zero errors. Do not add reported subtests to XML counts without checking serializer behavior.

Filesystem tripwire events: zero. Fake-only process tripwire events: 32 blocked Popen attempts. No process exemption was granted; no live receiver/model/production activation/GPU/ComfyUI work occurred.

Read-only XML comparison with current worker and pipe inventories proves all 32 expected process-boundary nodes are present among the 36 failures, with no unmatched expected boundary. They comprise 14 original worker/coordinator nodes, two dedicated worker probes, one installed-child-policy probe and 15 original pipe nodes. Positive evidence remains in their separately qualified exact process envelopes; the broad fake-only run itself remains red.

Four remaining failures reproduced in isolation: 0 passed / 4 failed, zero process/filesystem tripwire events. All three BinaryTests failures resolve the absent b99306303521e97e/codex.exe pin. The real binary-presence and real parser-contract tests genuinely require runtime qualification; the historical-hash negative test is a fake-capable fixture unnecessarily coupled to that absent binary. The offline parser replay requires absent runtime/ea4e/opencode/spool/run-d1eca109.stdout.jsonl. No stdout captures were found in that runtime subtree. Only installed Codex bin/bffc5354119c8421/codex.exe was inventoried; it was not executed or silently accepted as the frozen successor.

Prior binding-limit and durable-store failure groups do not appear in this completed failure inventory. This is evidence of their current absence, not a full-green or production-ready claim and not blanket proof of inherited/new classification for unrelated work.

Protected tracked diff fingerprint at evidence closure: 300ba6ec5733b6ae9e222b2f4615585cdbe122c82d546b766558a6fca8176fc7 (UTF-8 of git diff --binary lines joined with LF). Preserve protected WIP; do not stage it with this evidence-only checkpoint.

Next safe work: decouple the historical-hash negative fixture using existing qualified fake bytes; define the non-model Codex successor identity/contract qualification boundary; recover actual captured JSONL provenance or retain its replay as unavailable evidence. Never fabricate a historical capture, relabel guard-denied nodes as broad passes, silently roll production pins, weaken one-binding/durable-store semantics or infer production readiness from narrow gates.

Evidence-only checkpoint may commit this single report after scope/parent verification. No code qualification is asserted by this document. The active production-readiness goal remains incomplete.
