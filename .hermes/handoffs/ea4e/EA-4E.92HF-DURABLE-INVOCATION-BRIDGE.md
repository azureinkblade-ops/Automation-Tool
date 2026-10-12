# EA-4E.92HF Durable Invocation Bridge Reservation

Status: NON-LIVE / FAKE-ONLY. Parent: EA-4E.92HE.

`SQLiteAgentInvocationBridgeStore` reserves the pure 92HE cross-domain
identity in the delegation authority SQLite database before any future
invocation-authorization issuance. The accepted attempt is the primary key;
the derived execution-request ID is unique. Exact active replay returns the
same hash-checked artifact. Divergent executor binding, inactive delegation
or lease, prior receiver-start claim, or existing terminal state denies a new
reservation. The trusted time is sampled after obtaining the SQLite write
lock. `get` retains historical identity after cancellation but never grants
use. Concurrent independent callers insert one row.

The reservation is not issuance, activation, invocation authorization, a
receiver-start claim, process observation, or terminal proof. Its SHA-256 is a
corruption/replay checksum, not an attestation against a privileged writer.
The owner must still link the actual production authorization's exact
`execution_request_id` to this row, consume that authorization under the
existing durable policy, and prove the real receiver process and output.
The existing UUID-generating qualification executors remain unsuitable for
accepted delegated tasks.

Focused fake-only qualification: 10 passed, 0 failed. The first concurrency
test shared a thread-bound SQLite start connection and failed in its fixture;
using one independent start connection per caller corrected the test without
weakening the store. No real Codex, Kilo, OpenCode, model, Docker, GPU,
ComfyUI, or production activation was invoked. `PRODUCTION_READY=NO`.

The staged 92HF/92HE/92HD/92HC/capture/recovery/start ladder passed
75 tests, 0 failed, with one inherited `app.py` invalid-escape warning.
