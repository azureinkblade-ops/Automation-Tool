# EA-4E.92HW Ping Prompt Contract Correction

Status: NON-LIVE / CONTRACT-CORRECTION / PRODUCTION_READY=NO.

The committed 92HU ping command asked for plain PONG. That conflicted with
the existing `hermes.agent_ping_result/v1` verifier, which requires an exact
seven-key JSON object with task-input hash, receiver-receipt hash, expected
statement, empty output manifest, and one receipt-evidence entry. A model
following the old prompt would have been rejected by the result gate.

The command now asks for those exact fields and instance values in a single
quote-free positional argument compatible with the existing Kilo argv
builder. Tests check that the prompt carries both hashes and the receiver
statement, and that the corresponding structured candidate passes the
existing ping validator. This does not prove a model will obey the prompt;
malformed output must still fail closed.

Focused tests: 5 passed, 0 failed. No receiver/model, network, Docker,
GPU, ComfyUI, or production activation was invoked. Observed process and
terminal-byte provenance remain open.
