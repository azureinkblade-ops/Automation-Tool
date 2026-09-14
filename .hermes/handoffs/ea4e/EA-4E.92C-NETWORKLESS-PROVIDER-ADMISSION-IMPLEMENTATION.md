# EA-4E.92C Networkless Provider Admission Implementation

Parent: fddb4c9ac93813bede27111ed7606a9d5dba5db5.
Scope: acceptance-owned tools/ea4e92c_provider_call_control.py,
tests/hermes_core/test_ea4e92c_provider_call_control.py, this evidence.
No tools/hermes_core production modules changed; no live provider transport.

QualificationScope freezes run, source commit, transport/model binding, task
digest, effective request digest, exact endpoint/model and UTC time window.
Fixture provisioning explicitly writes qualification-only budget records into
an explicitly supplied isolated DurableInvocationAuthorizationStore. These
records are NOT production invocation authority. No production issuer,
activation, receiver registry or scheduler is invoked.

The gate denies wrong scope, method, endpoint/model, request digest, non-byte or
oversized input, cancellation/revocation flags and out-of-window time. It uses
the existing store's atomic claim/anchor integrity path before the required
injected callback. No default network transport, retry or refund exists.
Callback exceptions propagate after durable consumption. Independent fake
callback counts establish one forward under concurrent requests and duplicates.

Limits: this is a networkless admission primitive, not a deployed proxy or
complete live authority implementation. Cancellation/revocation flags are
request inputs, not persisted revocation ownership. Frozen effective-request
bytes are fixtures, not evidence of OpenCode's live generated messages. Caller
clock and injected callback remain trusted qualification collaborators.
No terminal provider-response/event journal is implemented in this slice.
Durable store reservation is reusable consumption evidence, not observed
provider model execution. No binding reseal, receiver bypass containment or
CPU-only Ollama qualification has occurred. None may be inferred from fake PASS.

Tests: 20 new cases cover valid/duplicate, twelve invalid request variants,
timeout and reopen, four-way concurrency, changed scope conflict, absent store,
required injection, precommit failure/rollback and postcommit failure before
anchor publication. Precommit failure calls no callback; postcommit failure
calls no callback and store reopen fails integrity. Existing durable-store
identity/rollback tests remain unchanged.

Working and independent staged exports each pass the ladder: 104 passed,
one explicitly deselected OS process node, zero fake process/filesystem events.
Staged source-only tree: 68abf9ecdbbdd46e994d8ca0dc6fa10fe5cdd970.
Export: .ea4e92c-index-a, tracked tools/tests/.gitattributes; evidence added later.
Command: pinned stage2-v2 Python, pytest -q, no cacheprovider,
fake-only/filesystem/report-host plugins, fresh basetemp,
test_ea4e92c_provider_call_control.py, test_ea4e32_restart_durable_authorization.py,
test_ea4e33a_store_rollback_detection.py, under tests/hermes_core;
-k 'not test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent'.
That OS test already has separate EA90 qualification, not an expected failure.

Post-commit independent ladder and fresh full fake-only regression are required
before final checkpoint acceptance. Keep raw inherited process-boundary and
missing historical capture failures visible. Subsequent source evidence is
recorded in Obsidian without amending this source checkpoint.

Next: terminal event/accounting contract and fake-only implementation, then
deployment/bypass and affected binding qualification. EA92 one-shot execution
remains on HOLD until all admission, model, no-GPU and authority gates pass.
No receiver/task/model, production activation, network callback, GPU/ComfyUI,
credential mutation or file deletion. Normal push requires exact commit approval.
