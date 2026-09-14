# EA-4E.92F Offline Provider HTTP Handler

Parent: e810c193fd7bba71533599bee2a960b7188d2841.
Acceptance-owned scope: tools/ea4e92f_offline_provider_http.py,
tests/hermes_core/test_ea4e92f_offline_provider_http.py, this evidence.

OfflineProviderHttpHandler accepts HTTP-shaped arguments, not sockets.
Only exact POST /v1/chat/completions and application/json are admitted.
Bodies must be UTF-8 JSON objects, at most 65,536 bytes, with the frozen
model and a messages list. Duplicate keys, nonfinite constants and streaming
are denied before budget consumption. The existing gate then checks exact
body digest, run identity, time window and cancellation/revocation flags.
Even equivalent JSON with different bytes requires a separately frozen scope.

Success uses the existing injected fake callback and durable accounting gate.
Admission failures return 403, durable-state failures 503, callback errors
502 without exception text. Unknown routes/methods/content types return
404/405/415; malformed and oversized requests return 400/413.
Abrupt BaseException remains unresolved; consumption is never refunded.
No listener, HTTP client, live forwarding or provider configuration is added.

23 new tests cover valid capture/duplicate denial, 20 pre-admission denials,
callback error privacy/no refund and ledger failure/no forwarding.
Working and independent staged source ladder: 168 passed, 1 OS-process
node excluded, 0 fake-only events, 0 filesystem events.
The first command referenced an incorrect predecessor filename and ran no
tests; the corrected command passed. No production behavior was weakened.

Source-only staged tree: 53ede1449218925e711dbc64359fdd2e9c24f549.
Retained export: .ea4e92f-index-a (tracked tools/tests/.gitattributes).
Command: pinned stage2-v2 Python -m pytest -q -p no:cacheprovider,
-p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard
-p tools.ea4e67n_nonlive_report_host; fresh basetemp; six dedicated files:
test_ea4e92f_offline_provider_http.py, test_ea4e92d_fake_provider_accounting.py,
test_ea4e92c_provider_call_control.py, test_ea4e56_nonlive_durable_accounting.py,
test_ea4e32_restart_durable_authorization.py,
test_ea4e33a_store_rollback_detection.py; exclude only
test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent.

Independent committed ladder and full raw fake-only suite still required.
Actual post-commit results go to Obsidian without amending this checkpoint.
Historical missing capture and inherited broad failures remain visible.

EA92E deployment HOLD remains: no listener ownership, actual OpenCode request
capture, persisted revocation owner, egress bypass prevention, CPU-only model
qualification or canonical deployment binding/reseal has been established.
Injected scope/clock/callback are trusted fixture inputs, not real authority.
No production activation, receiver/model/provider calls, GPU/ComfyUI, file
deletion or production module changes. Exact-SHA push approval is separate.
