# EA-4E.92LV three-agent shared-store handoff

Status: NON-LIVE / FAKE RECEIVERS / PRODUCTION HOLD.
Baseline: `2e18cbe79b6df94cf2caa5452c6660abc97a7a7f`.

One temporary SQLite authority database now carries three distinct
delegations from the same Hermes originator to Codex, Kilo, and OpenCode.
The test denies a different agent's mailbox claim for each delivery, records
one accepted receipt and verified synthetic result per intended receiver,
proves result replay does not duplicate delivery, reopens the authority
store, and has the originator claim and acknowledge exactly three distinct
result messages. This is a shared-state communication model, not three
independent per-agent fixtures.

Changed: `tests/hermes_core/test_ea4e92lv_three_agent_shared_store.py`.
Focused test: 1 passed, 0 failed. Adjacent receiver-lineage, text handoff,
Codex return, and three-agent recovery tests: 30 passed, 0 failed.

All receipts and results are synthetic; no actual Codex, Kilo, or OpenCode
receiver process or model was invoked. The test does not establish trusted
app launch, production activation, installed dependency closure, protected
issuer, or the exact mapped-byte invariant. Production remains HOLD.
