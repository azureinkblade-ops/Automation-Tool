# EA-4E.92IQ/92IR Pending Event and Reported Peer Comparison

Status: NON-LIVE / SUPPLIED-METADATA COMPARISON ONLY.
Baseline: `9b5a4af87d790ad6d4c98d31fb0d8da7338e2dee`.

The versioned fake gateway now requires a configured attempt ID and emits
that ID plus its pinned SSE digest in the one pending-request event. A new
strict parser rejects duplicate fields, malformed framing, noncanonical
peer addresses, and mismatched attempt/response identities. A pure
comparison ties that event to the durable **reported** Kilo container ID,
reserved candidate, generated task/receipt-bound SSE, and supplied
Docker-shaped two-member internal-network snapshot. Divergent IDs,
lineage, membership, running state, and peer IP deny.

This does not read the Docker daemon, attribute stdout to an inspected
container, attest socket ownership, validate the actual Kilo SDK request,
consume a real execution budget, or authorize release/start. The gateway
ID and running snapshot are caller-supplied. Both `peer_qualified` and
`release_authorized` remain false. The historical 92EW gateway is unchanged.

Focused new parser/comparison tests: 23 passed after a test-fixture correction
that avoided deep-copying a live SQLite connection. Affected Python ladder:
249 passed, zero failed. Node new/old gateway tests: 11 passed, zero failed.
Docker Desktop's Linux engine was unavailable for a read-only image inspect;
no image build/start or container action was attempted. No receiver, model,
credential, GPU/ComfyUI, result delivery, or production activation occurred.
Strict 92AT mapped-byte proof remains HOLD.
