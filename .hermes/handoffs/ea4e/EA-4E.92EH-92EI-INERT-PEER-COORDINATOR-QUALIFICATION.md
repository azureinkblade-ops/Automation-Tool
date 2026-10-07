# EA-4E.92EH/92EI inert peer coordinator qualification

Status: FAKE DRIVER + MOCKED CLI PASS / ONE-SHOT REAL PROBE PENDING
Baseline: `c6d8574b6b065709dde659f7c2eb7c8a31c984be`
Date: 2026-10-07 (America/Phoenix)

The coordinator consumes the frozen v2 plan, read-only image/name
preflight, exact created-object metadata check, and in-flight raw
peer-observation adapter. It starts only after the prestart check matches,
reads the gateway's `PEER_ACCEPTED` event, reinspects the fresh network and
both running containers while the request is pending, and sends one
`SIGUSR2` release only if the socket peer matches the client endpoint and
sole network membership. It requires both containers to exit zero and the
client log to be exactly `MARKER_MATCH\n`. Its `finally` path attempts
cleanup in client, gateway, network order using only returned create IDs.

The separate CLI driver uses argument arrays, not a shell. It requires an
exact `--approved-once` invocation with image ID
`sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`,
creates a fresh random run ID, tracks IDs returned by this run, restricts
start/inspect/cleanup to those IDs, and permits only one release signal to
the created gateway ID. The run ID is printed before mutation and any
remaining owned IDs are printed on failure. It does not invoke Kilo,
OpenCode, a provider, a model, GPU, or production activation.

The coordinator, mocked CLI driver, and adjacent pure/fake gates passed
87/87. No Docker object was created or started during these tests. This
does not prove Docker Desktop's actual inspect shape, socket address, or
cleanup outcome. If creation succeeds but its command times out before an
ID is returned, the driver cannot safely delete an unidentified object;
the labeled run ID must be reconciled manually. The real one-shot probe is
separately approved for exactly the v2 image, one internal network, two
temporary helpers, one gated release signal, and exact cleanup. Its
result must be recorded independently; a fake pass is not production peer
proof.

`FAKE_COORDINATOR=PASS`
`MOCKED_DRIVER=PASS`
`FOCUSED_TESTS=87_PASS`
`REAL_PROBE_EXECUTED=NO`
`KILO_RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
