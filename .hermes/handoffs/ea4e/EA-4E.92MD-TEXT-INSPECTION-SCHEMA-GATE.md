# EA-4E.92MD text inspection schema gate

Status: NON-LIVE QUALIFIED / PRODUCTION HOLD.
Parent baseline: `f691ca0cf9c30bf4f1b4ccaa58471eef37c8dea9`.

The 92MC host's Kilo/OpenCode `inspect()` initially treated the presence
of a durable terminal capture as terminal evidence, although the capture
store checks lineage and transport shape rather than the `agent_text`
result schema. A capture with a forged receiver receipt hash could be
reported as `TERMINAL_EVIDENCE_AVAILABLE` before `recover()` rejected it.

The host now runs the existing bounded text candidate validator on the
captured candidate before that positive inspection state. Forged receipt
hashes are denied by both inspection and recovery; no result or originator
message is written. Codex inspection already uses its terminal observation
validator. No capture/store or ping semantics changed.

Changed: `tools/hermes_core/agent_text_recovery_host.py` and
`tests/hermes_core/test_ea4e92mc_agent_text_recovery_host.py`.
Focused: 10 passed, 0 failed. Adjacent: 109 passed, 0 failed, one inherited
`app.py` invalid-escape SyntaxWarning. Tests use synthetic terminal text.
No agent/model, Docker mutation, UAC, GPU, ComfyUI, or production activation
occurred. Trusted app/issuer installation and live output compatibility
remain open; production remains HOLD.
