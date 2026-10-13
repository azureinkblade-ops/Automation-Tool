# EA-4E.92IO Versioned Ping Gateway Core

Status: NON-LIVE / SOURCE-ONLY / NOT AN IMAGE OR RUNNABLE GATEWAY.
Baseline: `a727e630cbd29adb81da426863729df6a4dea52b`.

A separate Node gateway core accepts a bounded SSE response only when its
SHA-256 and embedded task/receipt-bound ping fields match the expected
values. It retains one-request admission, bounded body digest reporting,
hold-until-release, timeout/abort denial, and replay denial. The historical
92EW fixed-string gateway was not modified. The new module exports a
factory only: no listener, entrypoint, Dockerfile, image build, receiver,
model, credential, or production activation.

Source-only Node tests: 4 new tests plus 6 historical gateway tests, all
passed. The 92IN Python fake gateway separately carries the real 92IM SSE
candidate through the durable one-use fake budget. These are complementary
synthetic checks; they do not attest the actual Kilo SDK request/response.

Next: bind a complete versioned gateway runtime/image and independently
qualify its immutable image identity, request-scoped peer/authority check,
response provisioning, terminal capture, and Kilo transport. No Docker
start or live receiver is authorized by this checkpoint. OpenCode remains
separate, and strict 92AT mapped-byte proof remains HOLD.
