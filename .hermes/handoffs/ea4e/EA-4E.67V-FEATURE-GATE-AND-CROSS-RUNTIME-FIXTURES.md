# EA-4E.67V Feature-Gate and Cross-Runtime Fixtures

Baseline: 42b36bf3ac0f6d56152143a095af0595d0844b70.
Scope: EA-4E.43 feature-gate and runtime 26B test modules, plus this evidence.

The feature-gate positive test reproduced DENY in isolation. It omitted
external execution authority and activation. It now supplies the existing
synthetic external_authority_and_activation helper for its exact receiver and
request. ALLOW and single fake executor call assertions remain unchanged.
No real authority/activation issuance ceremony is performed.

The 26B both-direction authorization test no longer binds receivers at once.
It binds/resolves OpenCode, rejects Kilo authorization against that handle,
tears down OpenCode, binds/resolves Kilo, and rejects OpenCode authorization.
It asserts binding counts one, zero, one. Both REceiver_BINDING_MISMATCH
assertions remain (exact production spelling RECEIVER_BINDING_MISMATCH).
Real durable policy and resolver are unchanged. No production lookup is mocked.

Candidate qualification: complete two repaired modules, EA-4E.41, filesystem
isolation, report host and process guard modules: 95 passed / zero guard events.
Command: python -m pytest -q -p no:cacheprovider
-p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard
-p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e67v-gate-a
with the six modules above and --tb=short. Verify independent staged-only and
actual committed exports before push.

No production/guard changes, real receiver/model, authorization ceremony,
GPU/ComfyUI, restart/deployment or file deletion. Successor WIP excluded.
Broad successor HOLD remains until a fresh broad qualification. Real-process
partition and missing binary/replay dependencies remain separately open.
