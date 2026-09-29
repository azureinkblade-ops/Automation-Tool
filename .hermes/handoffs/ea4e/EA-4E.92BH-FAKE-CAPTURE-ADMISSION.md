# EA-4E.92BH Fake Capture Admission

## Boundary

Non-live implementation from synchronized parent
`32cf41762707c65365c3be9dd880bf882144fc98`. The only source addition is
the acceptance-owned `tools/ea4e92bh_fake_capture_admission.py`, with its
dedicated tests. No production module, receiver registry, binding, application
host, provider configuration, or runtime state was changed.

This is a **fake receiver-start admission primitive**, not a qualified live
capture-only route. It has no process launcher, socket, provider transport,
model client, GPU, ComfyUI, or production activation API. The fake callback is
injected by tests; there is no default callback or automatic retry.

## Contract

`CaptureOnlyScope` binds run, receiver, source commit, executable/config
hashes, transport/model IDs, exact task hash, provider-budget identity, and a
maximum five-minute UTC window. It uses a distinct `capture-qualification-only`
durable authorization record, not production invocation authorization.
Explicit fixture provisioning is required. The durable store atomically claims
the one receiver-start budget before the injected fake capture is called.

Wrong receiver/source/binary/config/transport/model/provider budget/task,
expiry, cancellation and revocation deny before claim. Replay and concurrent
attempts allow at most one fake capture. Timeout, incomplete stream capture,
uncertain cleanup, empty stdout, or a provider-call count other than one never
refund the consumed budget. Missing durable state and anchor failure deny.

The existing EA92C/D/F provider gate remains separate; this slice does not
prove that a real receiver is confined to it, nor that a fake callback's
reported process/model counts are independent runtime observations.

## Verification

Pinned stage2-v2 Python, fake-only process guard, filesystem guard, non-live
report host, fresh basetemps:

- New capture gate plus EA92C/D/F provider gates: 80 passed, zero guard events.
- Capture gate plus provider/durable-accounting/restart/rollback predecessors:
  196 passed, one separately governed OS-process test deselected, zero guard
  events.
- Initial focused gate: 24 passed, one fixture failure due to expecting an
  integrity error for an absent anchor. The exact store-unavailable expectation
  was corrected without weakening production behavior.
- Canonical full fake-only Hermes Core: 4,539 passed / 35 raw inherited
  failures / six established OS-process tests deselected / 104 subtests
  passed. All 35 failure identities match the 92BF committed-source report;
  no added or missing failures. The fake-only guard denied 32 attempted
  subprocess starts and the filesystem guard reported zero events. Raw full
  suite status remains failed, not green. JUnit report:
  `.pytest-ea4e92bh-full-a/result.xml`, SHA-256
  `db0ee9eb5673fd0229679a73b53e65b86106d2ca25f9a48fbc61267fc54fcda9`.

Exact staged/committed verification is recorded in the paired Obsidian
continuation note after execution.

## Remaining Gates

Before any live OpenCode capture: qualify a real capture-only authority and
process owner without production activation; bind it to the one-call provider
gate and prove no direct provider bypass; freeze current source/binary/config/
model and affected contract IDs; establish CPU-only model execution or obtain
separate GPU authority; qualify durable raw stream/accounting and owned cleanup;
then obtain a fresh exact one-shot live authorization. None of those are
closed by the fake admission tests. EA92S exact mapped-byte HOLD is separate.
