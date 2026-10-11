# EA-4E.92GS Canonical Capture Binding

Status: NON-LIVE SOURCE CHECKPOINT. Parent is EA-4E.92GR. This is not a
current OpenCode provider qualification or a production activation.

## Contract

`hermes.opencode-capture-model-binding/v1` is a canonical, exact-field JSON
object hashed by SHA-256. It binds the receiver, provider and model IDs,
request-body model ID, clean HTTPS provider base URL, streamed chat route,
runtime/config/transport hashes, and credential/egress policy hashes. Its
fixed qualification status is `UNQUALIFIED_NONLIVE`. Parsing rejects
duplicate keys, extra/missing fields, noncanonical bytes, malformed digests,
and policy or endpoint drift. A changed bound field changes the binding ID.

The default-disabled 92GQ capture entry now parses supplied canonical binding
bytes and checks their hash, request model, runtime, config and transport
against the issued artifact before claiming its one-start credit. The
separate injected binding verifier from 92GR remains required; in this tree
it is test-only. The entry writes the exact binding bytes alongside each new
fake capture. `verify_bound_capture_v2()` requires and verifies those bytes,
the manifest identities, and a forwarded request's model. The frozen v2
manifest is not changed: older fake evidence still uses `verify_capture_v2`,
while a new binding-aware audit must call `verify_bound_capture_v2`.

## Evidence limits

The test fixture uses `opencode/nemotron-3-ultra-free` and
`https://example.invalid/v1` solely as inert synthetic material. It does not
attest the currently selected model, a real provider endpoint, credentials,
egress enforcement, CPU/GPU placement, or installed OpenCode request bytes.
The real isolated EA-4E receiver config still selects `ollama/qwen3:14b`.
No historical authorization or capture was rebound or relabeled. Captures
remain `FAKE_INJECTED_NONLIVE` and `acceptance_eligible=NO`.

The bounded fake-only artifact/store/SSE/capture/binding ladder passed 178
tests. Record the committed SHA and post-commit result in Obsidian.

## Next gates

1. Freeze an actual isolated Nemotron receiver config and exact provider
   endpoint/transport/credential/egress material, then hash and attest those
   bytes. Do not infer them from interactive sessions.
2. Implement independently trusted issuer verification and enforced provider
   egress plus process accounting. Fake callbacks cannot satisfy these.
3. Requalify the installed receiver and exact one-call streamed request in a
   separate bounded live packet. No current packet authorizes that call.

Until those gates pass, `PRODUCTION_READINESS=HOLD` and no receiver/model,
GPU, ComfyUI, or production activation may be invoked from this checkpoint.
