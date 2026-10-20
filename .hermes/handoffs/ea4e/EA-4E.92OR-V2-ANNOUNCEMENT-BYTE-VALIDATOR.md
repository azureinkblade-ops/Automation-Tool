# EA-4E.92OR v2 announcement byte validator

Status: NON-LIVE SYNTAX CHECK / AUTHORITY AND PRODUCTION HOLD.
Governing parent: `d7b8c69c9bea6c11d8c3e73ee098d19b67c2c436`.

The new `tools/ea4e92or_pipe_announcement_v2.py` checks a separate exact
v2 canonical byte format. It preserves the 92OJ v1 decoder and its refusal
of v2. The v2 format carries fixed-width lowercase, nonzero volume serial
and 128-bit file ID, and requires them to match independently supplied
expected values. All v1 identity, nonce, pipe-name, and deadline checks are
reapplied through the existing v1 validator after exact v2 field and byte
checks. The 1024-byte limit, duplicate-field rejection, and EOF-equivalent
whole-byte comparison remain fail closed.

This parser does not open a file, observe `FILE_ID_INFO`, authenticate an
elevated creator, attest the label/SACL, validate a manifest, establish a
nonce channel, or consume a durable one-shot ledger. A caller must not set
the expected file identity by copying the untrusted record. A parse PASS
is syntax only and cannot authorize pipe use, production activation, or
receiver/model execution.

Focused v1/v2 matrix: 77 passed. Broader adjacent matrix and staged-export
results are recorded in the commit verification, not inferred from this
source-only helper. No native file/pipe, Docker, receiver, model, GPU,
ComfyUI, or production action occurred.

Next: a source-only elevated retained-handle file identity and descriptor
readback candidate, with explicit creator/medium comparison and independently
authenticated attestation channel still required before any native probe.
