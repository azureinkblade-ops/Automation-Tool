# EA-4E.77 Historical Hash Fake Fixture

Governing parent: 7dd8a9e00938cf6c02dd1a3c3b4fd6519f3cceaf.

Scope: one test-fixture line in tests/hermes_core/test_codex_adapter.py.
BinaryTests.test_historical_binary_identity_is_not_the_successor_qualification now derives its configuration from the existing AdapterFixture fake-byte configuration, not default_trusted_config(). Historical expected hash/version, SHA-256 mismatch rejection, and zero-probe assertion are unchanged. No production source, executable pin, or real qualification assertion changed.

Fresh working-tree gate: 156 passed, 0 failed; filesystem tripwire events 0; fake-only process tripwire events 0. Gate uses no:cacheprovider, tools.ea4e67_fake_only_guard, tools.ea4e67m_filesystem_guard, and tools.ea4e67n_nonlive_report_host; the twelve EA75 predecessor fake suites plus the repaired historical-hash node. Fresh basetemp .pytest-ea4e77-fake-b.

Staged and committed source exports must independently pass the same 156-test gate before remote checkpoint acceptance. Actual SHA and post-commit results are recorded in the companion Obsidian checkpoint after verification, not presumed here.

EA76 historical broad result remains unchanged: 3384 passed, 36 failed, 6 deselected, 104 subtests passed. This focused repair does not revise that historical run or claim a new full rerun.

Still open: two real Codex binary/parser qualification tests depend on an absent frozen executable; the historical OpenCode replay requires a missing genuine stdout JSONL capture. The current installed executable is not silently substituted and no capture is fabricated. Thirty-two bounded-process failures in the fake-only broad run remain visible, with their separate qualification evidence.

No receiver execution, model invocation, production activation, GPU or ComfyUI activity authorized by this slice. Production readiness remains unproven. Protected successor WIP remains excluded; no files deleted.
