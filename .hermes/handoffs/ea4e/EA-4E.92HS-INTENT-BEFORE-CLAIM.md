# EA-4E.92HS Intent-Before-Claim Ordering

Status: NON-LIVE / FAKE-ONLY. Parent: EA-4E.92HR.

The non-executing text process intent must be reserved before the durable
invocation-authorization claim begins. Its SQLite reservation transaction
now rejects an existing `agent_invocation_claim_intents` row even when a
receiver-start fence has not committed. An injected failure after
authorization consumption but before the fence confirms that a late
process-plan reservation is denied and no intent row is created.

The affected fake-only ladder passed 176 tests, 0 failed before commit.
This enforces ordering only; it does not couple the two SQLite stores
atomically and does not grant process-start authority. No receiver/model,
network, Docker, GPU, ComfyUI, or production activation was invoked.
`PRODUCTION_READY=NO`.
