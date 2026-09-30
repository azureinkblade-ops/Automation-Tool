# EA-4E.92BN Capture-Qualification Authority Contract

Non-live contract checkpoint. Parent: `6912c38d31a4e2c97baa6dbd0537211807a938bb`.
This freezes a proposed implementation boundary, not an issued authorization.
No receiver, model, provider, network, GPU, ComfyUI, or native worker is permitted
by this document. EA92S mapped-byte proof remains REJECT/HOLD.

## Separate authority domain

The external Hermes capture issuer, not the app request handler, adapter,
receiver, or fake fixture, may issue a capture authorization. The runtime may
only validate and consume it. Its canonical schema is
`hermes.capture-qualification-authorization/v1` with exactly these fields:

`schema_id`, `authorization_id`, `issue_request_id`, `approval_id`,
`operator_id`, `run_id`, `receiver_id`,
`task_sha256`, `source_commit`, `executable_sha256`, `config_sha256`,
`transport_id`, `model_binding_id`, `provider_budget_id`, `issued_at`,
`expires_at`, `process_start_limit=1`, `nonce`.

The artifact is an exact-key UTF-8 JSON object with lexicographically sorted
keys, compact separators, no floats or duplicate keys, and SHA-256 over those
canonical bytes. Hashes are 64 lowercase hex characters; `source_commit` is
40 lowercase hex characters. IDs are nonempty ASCII strings of at most 128
characters, with only letters, digits, hyphen, underscore, and colon. All
authority and lineage IDs are distinct. `issued_at` and `expires_at` are
UTC timestamps with a `Z` suffix and second precision. `process_start_limit`
is the integer 1, not a boolean. No wildcard identity,
optional fallback model, replayed historical run ID, or inferred field is
allowed. The permitted receiver for this first contract is
`opencode-cli-agent`; this is not Kilo authority. The task bytes are compared
to `task_sha256`, not trusted from the receiver. TTL is at most five minutes,
with future issuance and `now >= expires_at` denied. The signed/reviewed
external issue request must bind the same fields, approval ID, and operator identity;
the issuer must reject an unreviewed request rather than synthesize one.

This artifact is **not** `ProductionInvocationAuthorization`. Neither the
production issuer nor production policy is widened. Production activation
must reject this schema and capture admission must reject production-scope
artifacts, even when other IDs happen to match. EA92BH's acceptance fixture
is also not an issuer for this schema.

## Durable state and ordering

Use a capture-owned SQLite store and anchor, separate from the production
`invocation_authorizations` table. The store has an independently pinned
instance ID and monotonic generation/epoch; rollback, missing anchor, wrong
instance, hash mismatch, or unknown schema denies. Persist the full canonical
artifact hash, issue-request hash, state, timestamps, and an integrity hash.
Do not compress the capture fields into the production store's
`execution_request_id` or a sidecar file. No implicit import or backfill from
EA4, EA92BH, or production-authorization rows.

An identical issue request may return the identical issued record. The same
issue ID or authorization ID with different canonical bytes is a conflict.
The only start-credit states are `ISSUED` and irreversibly `CONSUMED`; a
`REVOKED` flag can deny before claim or record revocation after claim, but
never restores start credit. A single immediate transaction must verify the
stored artifact, epoch/anchor, cancellation/revocation, clock, requested
identity and task hash, then change `ISSUED` to `CONSUMED`. Concurrent claims
yield exactly one success. Process start occurs only after the transaction
and anchor update are durable. If either commit or anchor publication is
uncertain, do not start. A start failure, crash, timeout, or uncertain PID
leaves the credit consumed. Recovery reports HOLD and never retries under
that authorization.

The capture coordinator owns request lifecycle and process cleanup. It must
not invoke `OpenCodeLiveBindingHarness` or build `ProductionActivation`.
Independent provider-call containment must reserve its one-call budget before
any upstream bytes, using EA92L's no-stream/no-retry/no-direct-egress policy.
The capture authorization's one-process limit does **not** prove one internal
provider call. Missing qualified config, package provenance, CPU/network
containment, or provider accounting denies before start.

## Qualification and unresolved live inputs

First implementation slice is data validation and isolated durable issue /
consume only, exercised with temporary stores and process-free fakes. Tests
must cover schema/cross-scope rejection, missing or changed identity/task,
expiry, cancellation/revocation, replay/conflict, concurrent claim, store and
anchor tamper/rollback, interrupted commit/anchor publication, and no credit
refund after uncertain start. A subsequent coordinator slice may be built
only after the same contract's admission ordering is proven. No module in
these first slices may import a real process launcher or provider client.

The actual issuer/operator identity, exact target executable/config/model,
trusted policy bytes, store/anchor path, provider/CPU/egress enforcement, and
secret-safe capture destination remain **unbound**. This contract's schema
freeze is not target-artifact freeze. EA92A's prospective capture, historical
EA4 replay, EA92S native creation, and production readiness remain HOLD.
Only an exact separately reviewed live packet after implementation and
qualification can grant one real invocation.
