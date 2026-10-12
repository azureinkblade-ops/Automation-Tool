# EA-4E.92HH Deterministic Delegated Issue Identity

Status: NON-LIVE / FAKE-ONLY. Parent: EA-4E.92HG.

The delegated issue-request builder now derives one stable `issue_request_id`
and nonce from the persisted bridge hash. The nonce is a replay identifier,
not a secret or authorization token. The explicit issue request still names
the bridge's exact execution request, receiver, executor binding, and
enablement. The preflight rejects caller-substituted issuer IDs and nonces,
as well as the identity substitutions covered by 92HG. Requested TTL is
bounded to the existing issuer maximum. A different TTL keeps the same
issue-request ID but changes the request hash, so the existing durable issuer
store will treat it as a conflict rather than a second authorization within
that same pinned store.

This builder can construct a request from an in-memory bridge; only the
preflight establishes that the bridge exists in the authority store and is
currently active. Neither builder nor preflight is wired into the general
production issuer. No authorization is issued, claimed, or consumed here.
The durable invocation-authorization store identity/anchor must be pinned by
the future owner; separate stores cannot be treated as one idempotency domain.
The cross-store cancellation race remains: successful preflight does not
authorize receiver start. A claim-time binding check and the one-shot start
fence remain necessary, with UNKNOWN after ambiguous irreversible claims.

Focused fake-only ladder: 28 passed, 0 failed. No real receiver/model,
network, Docker, GPU, ComfyUI, or production activation. `PRODUCTION_READY=NO`.
The broader delegated/predecessor/issuer/provisioner ladder passed 144 tests,
0 failed.
