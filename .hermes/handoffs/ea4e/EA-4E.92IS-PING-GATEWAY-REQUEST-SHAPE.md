# EA-4E.92IS Ping Gateway Request Shape

Status: NON-LIVE SOURCE CHECK / NO IMAGE OR RECEIVER.
Baseline: `07de2b23112eb3b01d1178562d53888c46a842b5`.

The versioned fake Kilo gateway now buffers at most 65,536 request bytes
and parses strict UTF-8 JSON before reporting a pending event. It requires
the dummy `ea4e-inert` model, the seven expected top-level fields and their
types, a two-message system/user shape with string/array content, and
streaming enabled. Bad JSON, invalid UTF-8, extra fields, wrong model, and
non-streaming requests return 422 without a pending report or release.

This is a Node-side semantic shape gate for the fake receiver path. It is
not a claim that a particular Kilo SDK version emits this request, nor an
exact duplicate-key/byte-equivalence proof against the Python parser.
The gateway still needs a qualified image, daemon-backed peer observation,
request-scoped authorization, and a separately approved bounded receiver
probe. No image build/start, receiver, model, credential, GPU/ComfyUI,
result delivery, or production activation occurred.

Python request-shape/dynamic-fake/integration tests: 40 passed.
Node versioned and historical gateway tests: 12 passed.
Strict 92AT mapped-byte proof remains HOLD.
