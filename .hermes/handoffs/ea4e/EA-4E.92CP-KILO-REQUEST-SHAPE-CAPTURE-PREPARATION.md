# EA-4E.92CP Kilo request-shape capture preparation

Status: NON-LIVE PREPARATION / NEW RECEIVER PROBE NOT AUTHORIZED
Baseline: `0be255aff32868e0388badb8b96f511d60df0356`

The 92CM one-shot probe established one streaming chat-completion request,
but intentionally did not retain body or headers. Its claim is consumed.
The 92CN fake-only gateway uses fixture JSON, not an observed Kilo body.

This checkpoint adds a bounded pure request-shape summarizer and connects it
to the dummy-only loopback provider's sanitized event. It accepts at most
65,536 UTF-8 JSON bytes, rejects duplicate keys and nonfinite constants,
requires the inert model and a bounded message list, and records only:

- body byte count and SHA-256 digest;
- types of an explicit fixed set of top-level fields, plus unknown-field
  counts without their names or values;
- message count, counts of fixed role labels and content kinds, and unknown
  message-field count;
- fixed booleans for expected model and streaming mode.

The event records only fixed route labels (`/v1/models`,
`/v1/chat/completions`, or `<other>`), method, status, boolean streaming
mode, and the shape summary. It never records request text, arbitrary
field names, URL query, authorization value, or a non-boolean stream value.
Tests inject a private sentinel into message content, an arbitrary field
name, an unknown path, and the stream field, and assert that neither stored
events nor printed output contain the sentinel or dummy token. The
summarizer is for an inert, fixed-prompt probe only: a digest can still
enable inference for low-entropy inputs and is not approved for production
prompt logging.

The source can now be reviewed before a *new* bounded probe is requested.
No new root, claim, Kilo process, provider/model call, production
activation, GPU, or ComfyUI use occurred here. A subsequent probe requires
its own exact executable/config hash, fresh home and claim, one-process
budget, timeout, egress-risk decision, and explicit operator authorization.
The old 92CM authorization and runtime home cannot be reused.

Local-token handoff is still a design gate. A future production gateway may
give Kilo only an attempt-bound local token, never the upstream credential;
its issuance, private delivery, revocation, lifecycle cleanup, and binding
to the durable attempt must be independently specified and tested. Merely
placing a token in Kilo config or an environment variable is not proof of
safe delivery. The existing free-model transport/model IDs cannot be
reused for the custom route, and EA-4E.92S mapped-byte proof remains HOLD.
