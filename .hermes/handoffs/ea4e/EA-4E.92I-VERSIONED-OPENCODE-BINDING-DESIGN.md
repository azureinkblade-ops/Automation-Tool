# EA-4E.92I Versioned OpenCode Binding Design

Status: DESIGN REVIEWED / CONTRACT FROZEN / NOT IMPLEMENTED.
Review baseline: e74c1518cf38d045824fee89df16cd088dce146c.
This proposal does not authorize registration, resealing, deployment or live use.

## Objective and Ownership

Replace ambiguous hash provenance with an explicit, reproducible preimage for
future governed OpenCode delegation. Hermes owns the reviewed binding manifest;
the receiver supplies no authority and cannot choose provider/config overrides.
EA92C-F remain acceptance fixtures, not a deployed control plane.
Historical binding IDs and qualification results remain unchanged.
Kilo, Studio Bible, Regional Hand Repair and image generation are out of scope.

## Identity and Serialization

Frozen schema: hermes.opencode-provider-binding/v1; artifact_version is integer 1.
The legacy binding is unversioned: do not describe this as a compatible v2 read.
model_binding_id = SHA256(UTF8(canonical_json(material))).hexdigest().
Use tools.hermes_core.hashing.canonical_json exactly: json.dumps(sort_keys=True,
separators=(',', ':'), ensure_ascii=True). No BOM or trailing newline.
The complete validated object below is the preimage; ID/signature/evidence text
are external, not additional preimage fields. Unknown/missing keys are denied.

Strict types: strings, exact integers for versions/budgets, exact booleans for
flags; booleans do not satisfy integer fields. No floats, nulls or coercion.
All SHA-256 fields are lowercase 64-hex. Strings are nonempty ASCII with no
leading/trailing whitespace or control characters. Duplicate JSON keys are denied.
Paths are exact absolute Windows strings, ordinary single separators after JSON
decoding, with no dot segments. No case folding, slash conversion or Path.resolve
inside hashing. The trusted composition layer supplies and validates exact paths.

The following is NON-LIVE FIXTURE MATERIAL, not a real deployment binding:

```json
{
  "schema_id": "hermes.opencode-provider-binding/v1",
  "artifact_version": 1,
  "receiver_id": "opencode-cli-agent",
  "receiver_class": "OPENCODE",
  "transport_contract_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "runtime": {
    "executable_path": "C:\\qualification\\opencode.exe",
    "executable_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "executable_version": "fixture-only"
  },
  "selection": {
    "provider_id": "ollama",
    "model_id": "fixture-model",
    "agent_id": "hermes-ea4e-opencode-receiver",
    "mechanism": "ISOLATED_CONFIG_AGENT_MODEL",
    "config_path": "C:\\qualification\\config.json",
    "config_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "ambient_config_allowed": false,
    "project_config_allowed": false,
    "task_model_override_allowed": false,
    "task_provider_override_allowed": false,
    "task_agent_override_allowed": false,
    "session_inheritance_allowed": false
  },
  "provider": {
    "package_id": "@ai-sdk/openai-compatible",
    "receiver_base_url": "http://127.0.0.1:19001/v1",
    "gate_route": "/v1/chat/completions",
    "upstream_base_url": "http://127.0.0.1:19002/v1",
    "credential_policy": "NO_PROVIDER_API_KEY",
    "stream_allowed": false,
    "redirect_limit": 0,
    "network_retry_limit": 0,
    "max_provider_calls": 1,
    "max_request_bytes": 65536,
    "max_response_bytes": 65536
  },
  "deployment": {
    "gate_contract_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "egress_policy_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "cpu_policy_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    "cleanup_contract_sha256": "1111111111111111111111111111111111111111111111111111111111111111"
  }
}
```

Offline fixture canonical length: 1,646 UTF-8 bytes.
Fixture digest: a7bfd43b26e706c78ae43b0c8880ce80dae5d82b167e2fac666c3c49ea57ff37.
This is the frozen golden fixture, never the registered deployment ID.

The fixture defines the exact recursive field set and types. Frozen constants:
schema/version, receiver ID/class, provider ollama, package, agent/mechanism,
gate route, credential policy, all false flags, zero redirects/retries and
max_provider_calls=1. Request/response limits are exact integers 1..65536.
Runtime version, model, paths, endpoint ports and identity/policy hashes vary
only under the stated validation rules and become part of the hash. Port text
is canonical decimal without leading zeros. No UNC/device-relative paths,
alternate drive syntax, repeated separators, empty components or dot segments.
Changing the key set, constants or validation policy requires a reviewed schema
revision. Hash sensitivity tests may hash mutated preimages diagnostically;
invalid material must never be returned as an admitted binding.

For this first local qualification design, URLs must use literal 127.0.0.1,
http, explicit port 1..65535, exact /v1, no userinfo/query/fragment, and distinct
receiver/upstream ports. No localhost/DNS, alternate host or URL normalization.
These restrictions are admission policy, not proof of OS egress containment.
NO_PROVIDER_API_KEY denies a composition needing provider credentials; expanding
credential scope requires another reviewed schema/policy, not secret literals.
Hash config file bytes, not a reconstructed JSON display; whitespace changes
require a new binding. Do not copy raw config/secrets into published evidence.
Contract/policy digests must resolve to reviewed artifacts, not arbitrary hashes.

## Why These Fields

Transport and executable identity bind the qualified receiver implementation.
Config bytes and exact selection prevent a path-only identity concealing a changed
model or endpoint. Receiver and upstream URLs explicitly bind the proposed gate
composition. Budgets/retry/stream settings expose one-call compatibility limits.
Separate policy hashes bind egress, CPU-only and cleanup requirements without
pretending that an identity hash itself enforces those requirements.

Do not include this manifest's source commit in its own preimage: that creates a
commit/hash cycle. Governing committed SHA belongs to the separate authorization
and evidence envelope, checked independently at use. Task/message hashes, run ID,
delegation ID, store ID/epoch, lease, authorization, attempt, launch, cancellation,
result and operator identities remain separate request-scoped artifacts.
The static model binding is not an authorization and never issues/claims a slot.

## Composition and Request Lifecycle

Trusted composition validates manifest, registered expected ID and referenced
policies; inspects exact runtime/config bytes without invoking the receiver;
and denies mismatch. No self-asserted receiver manifest can satisfy the check.
At the separately authorized live boundary, recheck the source/runtime/config
and store identities immediately before receiver admission. Mutable config and
policy files need enforced receiver access/immutability; two hashes alone do not
close time-of-check/time-of-use. Unenforced composition remains HOLD.

The gate must consume a durable one-shot reservation before any upstream bytes,
record real intent/entered/terminal evidence, and never refund on ambiguity.
Task text is not the effective provider body. Capture/generate the actual SDK
request in a fake-only harness before freezing exact request bytes for admission.
If OpenCode requires streaming, another route or multiple calls, this proposal
denies it; qualify compatibility separately rather than silently widening scope.
Persisted cancellation/revocation needs a trusted owner checked at reservation;
EA92C-F request booleans are not sufficient. Restart must not revive cancelled
authority or duplicate consumed work. No actual listener or egress policy exists
merely because their digest fields are present in this fixture.

## Frozen Acceptance Requirements

1. Golden canonical bytes and binding digest; repeatability and reordered keys.
2. Every leaf mutation changes the digest; ID/signature cannot enter the preimage.
3. Strict schema/type/path/URL/hash validation, duplicate keys, unknown fields,
   booleans-as-integers, nonfinite values and unsupported versions are denied.
4. Exact runtime/config byte mismatch blocks admission without launching anything.
5. Referenced policy missing/hash mismatch and absent current registry ID deny.
6. Legacy ID rejected as current binding; preserved historical records still read.
7. Fake request capture proves actual effective-message/body lineage; altered
   body, model, run, expired or cancelled/revoked request never reaches upstream.
8. Duplicate/concurrent/restarted admission forwards at most once; crash and
   timeout do not refund; durable corruption and ledger failure deny forwarding.
9. No subprocess/network/browser/model/GPU/MCP/scheduler capability in the pure
   contract module. Tests use temporary stores/config copies, never live state.
10. Downstream negative tests reject stale router/binding/activation/authority
    identities after the planned roll; Kilo behavior and identity remain unchanged.

Design inspection and fixture hashing are not execution-readiness qualification.
Implementation, complete dependency closure and reseal need separate acceptance.
Live provider configuration, containment changes, listener and model use remain
separately governed. Next artifact: EA-4E.92I-DEPENDENCY-AWARE-BINDING-ROLL-PLAN.md.
