# EA-4E.92IJ Durable Created-Container Report

Status: NON-LIVE / PRECLAIM-ONLY / START DENIED.
Baseline: `7edbc127dfaacca48a7e4b861a7601d887589911`.

The new SQLite store persists one **reported** created-container identity per
reserved Linux Kilo attempt. The report binds the current 92IB intent hash,
92IE candidate hash, syntactically valid container and network IDs, and
hashes of supplied container/image metadata. It requires a 92IG/92IH
candidate-metadata comparison first and rechecks authority, lease, intent,
and absence of a claim/fence inside a write transaction. Unique columns
prevent reuse of a reported container or network ID across attempts in the
same authority store. Readback checks columns against the canonical payload
and digest. Replay and competing writers are denied.

This is not a daemon attestation: the caller supplies the metadata and IDs.
It creates no Docker object, does no network call, and returns
`launch_authorized=False`. A future owner must bind these reports to fresh,
trusted daemon observations, exact containment policy, and the irreversible
one-shot claim/fence; it must never treat this record as a start permit.

Focused tests: 10 passed, including restart readback, invalid metadata,
post-cancellation readback, row/column tamper, and independent SQLite writers.
Affected 92DH/DP/DR/92H/92I ladder: 217 passed, 0 failed.
Post-commit verification must be recorded separately.

No receiver, model, fake gateway, credential, GPU, ComfyUI, or production
activation was used. OpenCode remains independently unqualified. The
accepted local-container profile does not close strict 92AT mapped-byte
proof, which remains HOLD.
