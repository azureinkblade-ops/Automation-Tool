# EA-4E.92NE canonical app-challenge frame

Status: NON-LIVE VALUE-ONLY CONTRACT / PRODUCTION HOLD.
Parent: `b20c3be9b075ad3b3dc809feb2384b695c726921`.

The 92NC app-instance challenge now has a canonical byte-frame format for a
future 92ND bounded native pipe reader. The frame is strict UTF-8 canonical
JSON, at most 512 bytes, with exactly four fields: schema version, ceremony
ID, challenge ID, and app-instance nonce. The three identities must be
distinct canonical lowercase UUIDs. Parsing rejects duplicate/extra fields,
noncanonical spacing/order, malformed encoding, wrong schema, and any
expected-value mismatch. A successful parse returns only a value object and
the frame SHA-256; it does not claim client, process, token, or pipe identity.

Changed files:

- `tools/ea4e92ne_app_challenge_frame.py`
- `tests/hermes_core/test_ea4e92ne_app_challenge_frame.py`
- this evidence file

Focused current-tree gate across 92NE and 92LQ: 73 passed, 0 failed.
The parser never creates a pipe, sends a challenge, invokes a receiver/model,
or issues authority. A native provider must source challenge and ceremony
from the independent issuer, read this frame on the same protected connection
under a real deadline, bind its client process/token to the retained app
instance, and maintain durable one-shot accounting. 92ND's overlapped I/O
and completion-aware cancellation requirements remain open. Strict 92AT
mapped-byte proof remains REJECT/HOLD, distinct from accepted 92DE local
container provenance. No Docker mutation, GPU/ComfyUI, or production action
occurred.
