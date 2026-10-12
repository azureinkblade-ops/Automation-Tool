# EA-4E.92HM Receiver-Start Fence Commit Faults

Status: NON-LIVE / FAKE-ONLY / PARTIAL. Parent: EA-4E.92HL.

The receiver-start fence store now has inert pre-commit and post-commit fault
injection points. A pre-commit failure rolls back the fence insert after
authorization consumption; the owner reports UNKNOWN and cannot retry. A
post-commit failure leaves exactly one durable fence, but the owner still
reports UNKNOWN because the caller did not receive a reliable commit result.
After reopening the stores, both replays remain UNKNOWN. Neither creates a
second authorization claim or fence.

The affected delegated, issuer, fence, and provisioner ladder passed 159
tests, 0 failed. Tests used temporary fake stores only. No real receiver,
model, network, Docker, GPU, ComfyUI, or production activation was invoked.

This does not establish trusted process identity, terminal-byte provenance,
cross-process crash recovery, or result return. A later process owner must
not treat a fence or a caller-supplied outcome as proof that a receiver ran.
`PRODUCTION_READY=NO`.
