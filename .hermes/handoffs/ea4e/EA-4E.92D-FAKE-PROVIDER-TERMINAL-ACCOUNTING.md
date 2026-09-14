# EA-4E.92D Fake Provider Terminal Accounting

Parent: 01b0c1f9c3a7726e68532e8031965b2372c32ec5.
Acceptance-owned scope: tools/ea4e92d_fake_provider_accounting.py,
tests/hermes_core/test_ea4e92d_fake_provider_accounting.py, this evidence.
Existing durable budget, observational ledger and production modules unchanged.

AccountedFakeProviderGate extends only the acceptance fixture admission gate.
After durable budget consumption, it records fake invocation intent/entered
using ProductionAccountingLedger in an explicitly isolated fixture database.
It calls the required injected fake callback once, exclusively creates a bounded
raw response and FAKE_QUALIFICATION manifest, flushes/fsyncs each, then records
completion. Ordinary failure records a failure; abrupt BaseException remains
unresolved. Neither path refunds consumption or admits a second forward.
Pre-forward ledger failure blocks the callback and leaves budget consumed.

The manifest binds scope identity, response bytes and SHA-256. Offline fixture
verification rejects response-only tampering. This is consistency checking,
not authenticated protection against replacement of both manifest and response;
live artifact hashes need an independently frozen evidence boundary.
Existing captures/manifests are never overwritten. Partial captures and errors
remain retained. The two files and ledger completion are not one atomic commit;
an interruption can leave authentic partial files plus unresolved events, never
an automatic success or retry. Clock and callback remain trusted fake inputs.

Nine new tests: completed/reopened ledger, callback timeout/no refund,
wrong-type/oversized response, existing capture, failed entered event,
interrupted callback/unresolved reopen, response tamper and existing manifest.
Initial fixture failures were incorrect count API keys and an oversized pytest
parameter ID causing a Windows setup path error. Canonical counts and explicit
short parameter IDs corrected fixtures; no production contract was weakened.

Working and final independent staged ladder: 145 passed, one separately
qualified OS process node excluded, zero fake process/filesystem events.
Final source-only staged tree: 5a3de9f330a411a77333aa9825d107f1938ed1fe;
retained export .ea4e92d-index-b, tracked tools/tests/.gitattributes.
The earlier 143-test gates preceded manifest/tamper additions and are historical.

Ladder: pinned stage2-v2 Python, pytest -q, no cacheprovider,
fake-only/filesystem/report-host plugins, fresh basetemp; files under
tests/hermes_core: test_ea4e92d_fake_provider_accounting.py,
test_ea4e92c_provider_call_control.py, test_ea4e56_nonlive_durable_accounting.py,
test_ea4e32_restart_durable_authorization.py,
test_ea4e33a_store_rollback_detection.py;
-k 'not test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent'.
Post-commit independent ladder and full raw fake-only regression required;
actual results will be recorded in Obsidian without amending source checkpoint.

Scope limits: simulated ledger model events are fixture observations, NOT real
provider/model execution. No live forwarding, process lifecycle cleanup,
persisted cancellation/revocation ownership, egress bypass containment, binding
reseal, credential readiness or CPU-only provider qualification implemented.
Those are next separate gates. Historical capture/test failure unchanged.
No receiver/model/provider requests, activation, GPU/ComfyUI, file deletion or
production edits. Exact-SHA normal push approval required after qualification.
