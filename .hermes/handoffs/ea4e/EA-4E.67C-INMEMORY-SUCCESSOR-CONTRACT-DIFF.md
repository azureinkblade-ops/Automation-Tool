# EA-4E.67C In-Memory Successor Contract Diff

Result: CANDIDATE HASH DIFF PASS / NOT PRODUCTION PROMOTION.
Baseline: `38e0fb7490fee8e17e537f895fde2a0f5389230b`.

The candidate is evaluated only inside a monkeypatch-scoped test. Existing
production pins, durable binding, authorization stores, and historical evidence
remain unchanged. The following baseline tests run after the candidate test
and pass, demonstrating restored module state.

## Candidate Identity

- Transport: `3c54405378c314e52afc95fbe055fd0a4249f0d78a515a108126b8e4fd73363e`.
- Executable binding: `b89f9f02f3e99cf70a98de8b4fb02b545e51855bb7340ed829ece749256b9be1`.
- Successor CLI version: 7.6.2; predecessor version: 7.5.16.
- Exact 13 candidate downstream IDs are asserted in the dedicated test's EXPECTED_IDS.
- Canonical transport material differs only in binary path, SHA-256, and version.
- Model, agent profile, permission policy, environment isolation, and lifecycle
  material are unchanged, not newly behavior-qualified by these hash assertions.

The existing successor helper still describes predecessor 7.5.15. The candidate
binding explicitly uses 7.5.16 and its current transport ID instead; blindly
reusing the current helper's predecessor fields would yield incorrect lineage.
Three circular-import cache IDs (17/21/22) are recomputed in dependency order.

## Safety and Verification

Python-level tripwire installed before collection blocks subprocess.Popen,
os.system, and socket connect/connect_ex. It reports observed attempts and fails
the session if any occur. It is NOT a universal OS sandbox; it does not cover
all native APIs or arbitrary code deliberately bypassing these functions.

Project Python command:
`-m pytest tests/hermes_core/test_ea4e67c_successor_candidate_contract_diff.py tests/hermes_core/test_ea4e34b_kilo_successor_contract_roll.py tests/hermes_core/test_production_kilo_qualification.py tests/hermes_core/test_kilo_live_binding.py tests/hermes_core/test_ea4e67a_successor_static_inventory.py tests/hermes_core/test_ea4e67a_metadata_probe.py -q -p no:cacheprovider -p tools.ea4e67_fake_only_guard --basetemp=<fresh-directory> --tb=short`.

Final combined result: 54 passed / 0 failed / 0 tripwire events.
This is a bounded baseline and candidate diff, not the complete Hermes regression
gate or a full source/artifact dependency closure.

## Next Qualification Slice

1. Freeze the complete affected source/artifact/test closure, not just these 13 IDs.
2. Build successor-specific production changes in an isolated clean candidate,
   preserve 7.5.16 historical identities, and use correct predecessor lineage.
3. Align credential-preflight transport and circular cache IDs; reseal downstream
   artifacts atomically. Do not weaken exact-path/hash checks or durable-store rules.
4. Replace historical installed-binary checks with explicitly classified historical
   evidence plus current successor tests; do not hide genuine regression failures.
5. Run fake-only successor mismatch/replay/reconstruction tests, predecessor ladder,
   full Hermes tests, and committed-tree verification before production deployment.
6. Only then renew the expired binding and freeze a fresh bounded live-task envelope.

Checkpoint scope: the tripwire plugin, candidate test, and this evidence only.
No receiver task, model invocation, durable state mutation, GPU, or ComfyUI work.
