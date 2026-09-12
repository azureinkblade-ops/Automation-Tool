# EA-4D.4F-R11 - Agent-to-Agent Governed Delegation Integration

Status: ACCEPTED / FROZEN

Authority granted by this packet: design only

Implementation authority: NOT GRANTED

Live agent invocation: NOT AUTHORIZED

GPU / ComfyUI authority: OFF

Commit / push: NOT AUTHORIZED

## 1. Course correction

EA-4D.4F exists to connect governed agents. Regional Hand Repair was a bounded
qualification workload used to prove parts of the Execution Authority chain. It
is not the EA-4D.4F product objective and is not a dependency of this design.

The R8-R10 Regional Hand Repair evidence remains valid as qualification evidence
for authorization, claim, attempt, routing, launch admission, start-result
reconciliation, execution projection, replay resistance, and durable lineage.
It does not determine the agent integration contract or roadmap.

Studio Bible, ComfyUI, image generation, and Kilo-owned image-pipeline work are
outside this packet. No part of R11 may modify or redesign those systems.

## 2. Objective

Freeze the first real contract by which one named agent asks Hermes to delegate
bounded work to another named agent, the receiver accepts or rejects the exact
task under the exact authorization, and Hermes verifies and returns the result
without either agent fabricating authoritative state.

The governing flow is:

```text
Originating Agent
    -> DelegationRequest
Hermes Governance + Execution Authority
    -> authorization / claim / ExecutionAttempt
WorkerRouter
    -> named receiving agent + runtime binding
Receiving Agent
    -> DelegationAcceptance
    -> bounded execution
    -> DelegationResult + evidence
Hermes
    -> lineage verification / terminal state
    -> ResultDelivery to originator or next authorized agent
```

## 3. Existing mechanics retained

R11 reuses, rather than replaces, these proven mechanics:

- Hermes remains the sole owner of authoritative governance state.
- Acceptance and execution authorization remain separate.
- `ExecutionAuthorization` binds operation, input hash, worker class, attempt
  limit, runtime limit, policy, and authority actor.
- `ExecutionClaim` atomically reserves authorization consumption.
- `ExecutionAttempt` records one authorized attempt and its complete lineage.
- `WorkerRegistry` and `WorkerRouteDecision` select only registered identities.
- `ExecutionStartReservation` and `ExecutionLaunchAttempt` separate reservation
  from the single external launch side effect.
- Runtime bindings resolve symbolic worker identity to a trusted adapter.
- `ExecutionStartResult` records only whether a runtime definitively started or
  failed.
- Idempotency and reconciliation prevent a lost acknowledgement from causing a
  blind second launch.
- Hermes projection and evidence stores remain authoritative; agent output is
  untrusted until validated.

## 4. Gap being closed

The current chain stops at runtime start and `EXECUTING` projection. It does not
yet define:

- a canonical delegated-task artifact;
- originator and receiver agent identities;
- receiver acceptance or rejection;
- the authority lease visible to the receiver;
- terminal result and evidence return;
- originator result delivery;
- agent-specific cancellation, crash, and retry semantics.

For governed agent work, `runtime started` is not sufficient proof that the
receiving agent accepted the delegation. R11 therefore adds an agent-acceptance
gate before agent work may be considered `EXECUTING`.

## 5. Participating identities and roles

### 5.1 Logical principals

| Principal | Initial identity | Role | Authority |
|---|---|---|---|
| Originating agent | `hermes-primary-agent` | Creates a delegation request | May request only; cannot authorize, route, or mutate state |
| Governance owner | `hermes-governance` | Validates task and governance lineage | Sole governance state owner; cannot impersonate an agent |
| Execution authority | `hermes-execution-authority` | Issues/revokes bounded execution authorization | May authorize under policy; does not execute agent work |
| Router | `hermes-agent-router` | Selects an eligible named receiver | Deterministic routing only; no execution authority |
| First receiver | `codex-cli-agent` | Accepts and executes one canonical delegated task | Executes only the capability lease in the envelope |
| Human operator | existing authenticated operator identity | Approves policy-gated delegation where required | Does not become the receiving agent |

The same model later supports `kilo-agent`, reviewer agents, or other registered
agents. Agent identity, worker identity, and runtime binding identity are
related but distinct fields and must never be inferred from executable paths.

### 5.2 Why Codex is the first receiver

The installed Codex CLI exposes a supported non-interactive interface:

- prompt via stdin;
- explicit working directory;
- explicit sandbox policy;
- JSONL event output;
- optional final-output JSON Schema;
- durable or ephemeral session modes.

The installed Kilo Code extension exposes VS Code commands and an Agent Manager,
but discovery found no stable unattended CLI or local API contract. UI driving
would not provide a reliable acceptance, idempotency, or result boundary. Kilo
is therefore a planned adapter after a supported callable interface is proven.
This is a transport decision, not a change in Kilo's product ownership.

## 6. Canonical delegated-task envelope

The immutable `DelegatedTaskEnvelope` is created before execution authorization.
R12 must reuse `tools.hermes_core.hashing.canonical_json` and
`sha256_payload`; it must not introduce another canonicalizer.

Canonical encoding contract:

- the artifact is a JSON object encoded from the canonical string as UTF-8;
- object keys are lexicographically sorted and separators are exactly `,` and
  `:` with no insignificant whitespace;
- `ensure_ascii=True` is retained for compatibility with existing Hermes
  artifacts, so non-ASCII text is represented by JSON escapes before UTF-8
  hashing;
- duplicate object keys, NaN, infinity, binary values, and floats are forbidden;
- integers are base-10 JSON integers with no leading zero and booleans are JSON
  `true` / `false`;
- every schema field is present; an absent optional value is canonical JSON
  `null`, never an omitted field or empty-string substitute;
- text is Unicode NFC with CRLF/CR normalized to LF; trailing whitespace is
  significant and therefore validation rejects it rather than silently changing
  it;
- maps are sorted by the canonicalizer; set-like lists are deduplicated and
  sorted before canonicalization;
- ordered lists carry an explicit zero-based `ordinal`, with unique contiguous
  ordinals, and are canonicalized in ordinal order;
- timestamps are UTC RFC3339 at whole-second precision in
  `YYYY-MM-DDTHH:MM:SSZ` form;
- hashes are lowercase 64-character SHA-256 hexadecimal strings.

Paths do not enter identity as absolute host paths. A path reference is a
workspace-relative POSIX path or a content-addressed URI plus SHA-256. It must
not contain a drive, leading slash, `.`/`..` segment, symlink-dependent
resolution, username, or host-specific workspace root. Secrets are prohibited.

Required fields:

```text
artifact_type                 = "hermes.delegated_task"
artifact_version              = "1"
delegation_id
delegation_revision
originator_request_id
task_id
parent_task_id                = optional
originator_agent_id
requested_target_agent_id
operation
objective
instructions
input_manifest[]              = typed references + sha256 + media type
task_input_hash               = hash of canonical task inputs
scope                         = read/write paths, tools, network, time budget
expected_result_schema_id
expected_evidence[]
requested_at
expires_at                    = optional
redelegation_allowed          = false by default
artifact_hash
```

`delegation_id` is the full lowercase SHA-256 digest prefixed by `delegation-`,
derived from this canonical identity preimage:

```text
{
  "artifact_type": "hermes.delegation_identity",
  "artifact_version": "1",
  "delegation_revision": <non-negative integer>,
  "originator_agent_id": <string>,
  "originator_request_id": <string>
}
```

The same originator request and revision must resolve to the same delegation.
A changed objective, input, scope, or target under the same identity is a
conflict, not a new delegation.

`task_input_hash` is SHA-256 over only the content-bearing task material:
`operation`, `objective`, `instructions`, canonical `input_manifest`,
`expected_result_schema_id`, and canonical `expected_evidence`. It excludes the
target agent, worker/runtime identities, authorization, scope, timestamps, and
all execution identities. The envelope `artifact_hash` covers every canonical
envelope field except `artifact_hash` itself, including target, scope, and
timestamps. Timestamps are therefore integrity-bearing metadata but do not
derive `delegation_id` or `task_input_hash`.

The existing execution chain binds the complete assignment by requiring:

```text
ExecutionAuthorization.authorized_scope.input_hash
    == DelegatedTaskEnvelope.artifact_hash
ExecutionAttempt.input_hash
    == DelegatedTaskEnvelope.artifact_hash
ExecutionLaunchAttempt.input_hash
    == DelegatedTaskEnvelope.artifact_hash
```

The envelope contains references and hashes, not arbitrary host credentials or
ambient authority. The receiver must be able to reconstruct exactly what it was
asked to do from the envelope and its declared inputs.

## 7. Identifier separation

| Identifier | Meaning | Cardinality |
|---|---|---|
| `delegation_id` | One logical assignment from an originator to a requested target | One per originator request revision |
| `task_id` | Hermes-governed parent work item | May own multiple delegations |
| `authorization_id` | One policy decision permitting bounded execution | One or more over a delegation's lifetime |
| `claim_id` | Atomic reservation of one authorization | One per consumed authorization claim |
| `attempt_id` | One authorized execution attempt | Up to authorization attempt limit |
| `route_id` | Deterministic receiver selection for an attempt | One active route per attempt |
| `launch_attempt_id` | One admitted external launch side effect | At most one per start reservation |
| `runtime_run_id` | Receiver runtime's own run identity | Zero or one per successful launch |
| `result_id` | One immutable receiver result for an attempt | At most one terminal result per attempt |
| `result_delivery_id` | Hermes delivery of a verified result to an originator | Idempotent per result and recipient |

No identifier may stand in for another. In particular, a launch attempt does
not prove receiver acceptance and a runtime run does not prove task completion.

## 8. Authority propagation

Hermes does not transfer governance or authorization authority to the receiver.
After authorization, claim, attempt, and named routing, Hermes issues one
immutable `DelegatedCapabilityLease` bound to:

- `lease_id`, `artifact_type="hermes.delegated_capability_lease"`, and
  `artifact_version="1"`;
- issuer `hermes-execution-authority`;
- `delegation_id` and envelope hash;
- `authorization_id` and authorization hash;
- `attempt_id` and attempt hash;
- `route_id` and route hash;
- exact receiving `agent_id` and worker descriptor hash;
- allowed operation and tools;
- permitted read/write paths;
- network policy and approved hosts;
- maximum runtime and expiry;
- result schema and evidence requirements;
- `redelegation_allowed=false`;
- `issued_at`, `not_before`, and `expires_at`.

`lease_id` is `lease-` plus the full SHA-256 of the canonical lease preimage
excluding `lease_id` and `artifact_hash`. The final `artifact_hash` covers the
canonical artifact including `lease_id` and excluding only `artifact_hash`.
There is at most one lease identity for an attempt/route pair. Exact replay
returns it; divergent replay conflicts.

The lease is a capability boundary, not a role promotion. A receiver may not
change Hermes state, broaden scope, select another agent, mint a child task, or
reuse the lease for another attempt. Any future child delegation requires a new
Hermes request, separate policy decision, and explicit parent lineage.

The lease artifact is append-only. Revocation and cancellation are separate
Hermes-owned durable events. A lease may be renewed only before acceptance;
renewal creates a new authorization, attempt, route, and lease identity. An
expired or revoked lease can never authorize a new capability use. If lease
state cannot be verified, the adapter and receiver fail closed.

Before each capability-bearing operation and before terminal result emission,
the receiver must check the lease state through the trusted adapter. Expiry or
revocation before acceptance requires rejection. Expiry or revocation during
execution requires stopping at the next safe cooperative boundary, performing
no further delegated writes/tool calls, and returning a `CANCELLED` result with
reason `LEASE_EXPIRED_DURING_EXECUTION` or `LEASE_REVOKED_DURING_EXECUTION`.
Such a result may carry recovery evidence but cannot be promoted as `SUCCEEDED`.

## 9. Routing contract

Routing uses the existing versioned `WorkerRegistry` and deterministic
`WorkerRouteDecision`. R11 adds these agent constraints:

- the selected worker descriptor must bind `agent_id` explicitly;
- if `requested_target_agent_id` is set, routing must select that exact active
  identity or fail closed;
- capabilities and allowed operations must satisfy the capability lease;
- the route binds the delegated-task hash and exact registry snapshot;
- executable path, window title, model name, or free-form command may not define
  identity;
- route fallback to a different agent requires policy authorization and a new
  route artifact. Silent substitution is prohibited.

## 10. Acceptance and rejection protocol

After runtime start, the receiver must emit exactly one immutable
`DelegationReceipt` for the attempt:

```text
receipt_id
delegation_id
delegated_task_hash
capability_lease_id / hash
authorization_id / hash
attempt_id / hash
route_id / hash
launch_attempt_id / hash
receiver_agent_id
receiver_descriptor_hash
receiver_implementation
receiver_version
runtime_run_id
outcome                     = ACCEPTED | REJECTED
reason_code                 = required for REJECTED
reason_summary              = bounded, no secrets
received_at
decided_at
artifact_type               = "hermes.delegation_receipt"
artifact_version            = "1"
artifact_hash
```

`receipt_id` is `receipt-` plus the full SHA-256 of the canonical receipt
preimage excluding `receipt_id` and `artifact_hash`; the final artifact hash
includes `receipt_id` and excludes only `artifact_hash`. The accepted task hash
must equal the persisted envelope artifact hash.

The receipt is persisted in its own immutable `delegation_receipts` table, not
only as a mailbox event. The receiver proposes it through the adapter; only
Hermes validates and inserts it. A hash-linked `RECEIPT` mailbox message is
written in the same SQLite transaction so delivery history is reconstructable.
The unique key is `attempt_id`. Exact replay returns the existing receipt;
same-attempt divergent content is an integrity conflict and no state advances.

Frozen rejection reason codes are:

```text
UNSUPPORTED_ARTIFACT_VERSION
INVALID_ENVELOPE_HASH
INVALID_LINEAGE
INVALID_OR_EXPIRED_LEASE
REVOKED_OR_CANCELLED
WRONG_RECEIVER
UNSUPPORTED_OPERATION
INPUT_MISSING_OR_HASH_MISMATCH
SCOPE_UNSUPPORTED
RESULT_SCHEMA_UNSUPPORTED
INTERNAL_RECEIVER_ERROR
```

Acceptance means only that the exact receiver has validated the envelope,
lineage, capability lease, supported operation, and required inputs. It does not
mean the work succeeded.

Hermes may project governed agent work to `EXECUTING` only after:

1. a definitive `ExecutionStartResult(STARTED)`;
2. a valid receipt with `ACCEPTED`;
3. exact lineage match through delegation, authorization, attempt, route,
   launch, receiver identity, and runtime run.

`REJECTED` is terminal for that attempt and may be retried only under retry
policy. Missing or malformed receipt is unresolved, never implied acceptance.
If cancellation/revocation is durable before the receipt transaction commits,
an `ACCEPTED` receipt is rejected and the attempt terminates cancelled. If
acceptance commits first, later cancellation follows the cooperative execution
rule. These orderings are decided by SQLite transaction order, not wall-clock
comparison.

## 11. Handoff mechanism

### 11.1 Contract

The contract is transport-neutral. Hermes persists the canonical envelope and
lineage before delivery. A transport adapter may carry only the frozen envelope,
capability lease, and declared inputs. Transport output is untrusted until
normalized into a receipt or result artifact.

Hermes uses one SQLite authority database for delegation, lease, receipt,
result, and mailbox state in R12. No receiver receives direct database write
access. Messages are immutable and append-only in `agent_mailbox_messages`.
Claim/acknowledgement transitions are append-only rows in
`agent_mailbox_delivery_events`, each binding the previous event hash. A
disposable `agent_mailbox_delivery_projection` may cache current state, but the
hash-linked events are authoritative and acknowledgement never mutates message
evidence.

Every message has:

```text
message_id
mailbox_id                  = recipient agent id
mailbox_sequence            = monotonically increasing per mailbox
message_type                = DELEGATION | RECEIPT | PROGRESS | RESULT |
                              CANCELLATION | REVOCATION | RESULT_DELIVERY
sender_agent_id
recipient_agent_id
delegation_id
attempt_id                  = nullable where not yet assigned
idempotency_key
payload_schema_id
payload_hash
created_at
artifact_version            = "1"
artifact_hash
```

`message_id` is `mailmsg-` plus the full SHA-256 of the canonical
`mailbox_id` and `idempotency_key`. Exact replay with the same payload hash
returns the existing message. Same key with a different payload hash is a typed
conflict. Ordering is the committed `mailbox_sequence`; timestamps do not break
ties or establish authority.

Delivery state is `PENDING | CLAIMED | ACKNOWLEDGED | DEAD_LETTER`. Claiming is
an atomic, expiring lease owned by the registered recipient. A crash after read
but before acknowledgement releases by expiry and re-delivers the same message,
never a new message. Acknowledgement binds message id/hash, recipient, claim
token, and acknowledged time. Originators acknowledge `RESULT_DELIVERY` only;
receivers acknowledge `DELEGATION`, `CANCELLATION`, and `REVOCATION`. Progress
is optional, monotonic per attempt, and never authoritative.

Each authoritative artifact and its corresponding mailbox message is inserted
in one local SQLite transaction. External process invocation is outside that
transaction and is protected by the already frozen launch idempotency and
reconciliation boundary. No distributed transaction is introduced. Conflicting
or tampered payloads are retained as integrity evidence and fail closed.
R12 retention is indefinite; pruning/compaction is explicitly out of scope.

### 11.2 First adapter

The first implementation target is a `LOCAL_AGENT_PROCESS_ADAPTER` for
`codex-cli-agent`:

- Hermes writes delegation state to its SQLite authority store before spawn.
- The adapter supplies the canonical request on stdin, never in a shell-built
  command string.
- Codex runs in an explicit working directory and least-authority sandbox.
- `--json` supplies machine-readable events.
- `--output-schema` constrains the final response to the result contract.
- stdout/stderr are bounded and captured as non-authoritative transport
  evidence; secrets are redacted.
- the adapter owns a durable idempotency registry keyed by the admitted launch
  attempt's idempotency key.
- no shell invocation or UI automation is permitted.

The reviewed executable on 2026-08-27 is:

```text
C:\Users\David\AppData\Local\OpenAI\Codex\bin\d0097be4feba73d0\codex.exe
version: codex-cli 0.150.0-alpha.8
sha256: 09d6723925e724edf0bbbbc7b9e204526e0fb1462c86bd2a4997311fd5071eba
```

The path is discovery metadata, not agent identity. A future adapter binding
must pin executable SHA-256, reported version, adapter version, and allowed argv
shape. A changed binary/version fails closed pending requalification.

Frozen unattended argv shape for the later adapter qualification is:

```text
codex.exe exec
  --json
  --output-schema <trusted-schema-file>
  --output-last-message <adapter-owned-output-file>
  --ephemeral
  --ignore-user-config
  --ignore-rules
  --ask-for-approval never
  --sandbox read-only
  --cd <frozen-fixture-worktree>
  --disable shell_tool
  --disable browser_use
  --disable browser_use_external
  --disable browser_use_full_cdp_access
  --disable computer_use
  --disable image_generation
  --disable apps
  --disable plugins
  --disable hooks
  --disable multi_agent
  -
```

The canonical delegation request is supplied on stdin as data. The schema,
working directory, executable, argv, environment allowlist, and sandbox are
trusted binding configuration and cannot come from the delegated task. Authentication
uses the existing Codex account through `CODEX_HOME`; credentials are not placed
in the envelope, environment evidence, or logs.

R12D must use `codex debug prompt-input` or an equivalent pinned-version
inspection to prove the model-visible tool list contains none of the disabled
execution/browser/image/plugin capabilities. If a no-tool invocation cannot be
mechanically demonstrated, Codex receiver qualification is `HOLD`; prompt text
alone is not a capability boundary. The harmless proof fixture is embedded in
the canonical stdin request, so the receiver requires no filesystem tool.

`--json` writes JSONL transport events to stdout; diagnostics are captured from
stderr separately. The final response must also validate against the pinned
output schema. Exit code zero alone does not prove task success, and nonzero
exit is an invocation failure unless a valid terminal artifact was already
durably captured. The adapter enforces timeout and cancellation by owning the
process handle and using bounded terminate/kill; Codex exposes no reviewed
per-command timeout or cancellation protocol.

The adapter creates and persists `runtime_run_id` before spawn and binds it to
the launch attempt/idempotency record. Any Codex thread/session identifier
observed in JSONL is optional transport metadata, not the Hermes runtime identity.
This avoids depending on an undocumented event field while preserving a stable
machine boundary. R12D must qualification-test the minimal JSONL event parser
against the pinned CLI before any live agent invocation.

### 11.3 Deferred adapters

- Kilo: deferred until a supported CLI/API/ACP endpoint can accept a canonical
  envelope and return a stable machine-readable result.
- MCP: a future adapter is allowed, but MCP connection success alone does not
  satisfy delegation receipt, capability lease, terminal result, or durable
  idempotency requirements.
- HTTP: allowed only through a registered loopback/approved-host binding with
  authenticated receiver identity and the same artifact contracts.
- Filesystem inbox: may be used as a delivery transport only with atomic rename,
  hash verification, durable acknowledgement, and SQLite authority state. A
  loose Markdown handoff file is not an execution protocol.

## 12. Execution status model

Hermes owns the authoritative delegation projection:

```text
REQUESTED
VALIDATED
AWAITING_EXECUTION_AUTHORIZATION
AUTHORIZED
CLAIMED
ROUTED
LAUNCH_ADMITTED
RUNTIME_STARTED
RECEIVER_ACCEPTED
EXECUTING
RESULT_REPORTED
RESULT_VERIFIED
COMPLETED
```

Terminal alternatives:

```text
REJECTED_BY_POLICY
REJECTED_BY_RECEIVER
FAILED_TO_START
FAILED
CANCELLED
EXPIRED
INCONCLUSIVE
```

Projection is derived from immutable artifacts and durable events. Agents may
report status, but cannot directly write the projection.

Optional progress reports are non-authoritative and must bind delegation,
attempt, receiver, monotonic sequence number, and timestamp. A missing heartbeat
is not proof of failure or permission to duplicate execution.

## 13. Result and evidence return

The receiver emits one `DelegationResult`:

```text
result_id
delegation_id / delegated_task_hash
authorization_id / hash
attempt_id / hash
launch_attempt_id / hash
receipt_id / hash
receiver_agent_id / descriptor_hash
runtime_run_id
outcome                     = SUCCEEDED | FAILED | CANCELLED
result_payload              = matches expected result schema
output_manifest[]           = typed references + sha256 + media type
evidence_manifest[]         = typed references + sha256
started_at / completed_at
error_code / error_summary  = required for FAILED
artifact_hash
```

`result_id` is `result-` plus the full SHA-256 of the canonical result preimage
excluding `result_id` and `artifact_hash`; the final artifact hash includes
`result_id`. The unique key is `attempt_id`. Exact replay returns the stored
result; a divergent result for the same attempt is an integrity conflict.

Hermes verifies schema, hashes, receiver identity, scope compliance, lineage,
and evidence requirements. `SUCCEEDED` from an agent is a claim until Hermes
records `RESULT_VERIFIED`.

Hermes then creates an idempotent `ResultDelivery` addressed to the originating
agent. The originator receives the verified payload, terminal disposition, and
evidence references. It does not receive execution credentials or the receiver's
ambient session state. If the originator is unavailable, the result remains in
a durable Hermes-owned mailbox and may be acknowledged later without rerunning
the delegated work.

`result_delivery_id` is `delivery-` plus SHA-256 of the canonical
`result_id`, `recipient_agent_id`, and `delivery_revision=0`. Delivery retries
reuse that identity. A later authorized redirection uses a new recipient and a
new identity; it does not alter the result.

## 14. Completion and failure semantics

- `COMPLETED` requires a verified `SUCCEEDED` result and all required evidence.
- Receiver `FAILED` produces a durable failed attempt; it does not automatically
  consume another attempt.
- A transport error before definitive start is `FAILED_TO_START` only when the
  runtime adapter proves failure.
- Unknown launch or lookup state is `INCONCLUSIVE` and must reconcile under the
  existing idempotency key before any retry.
- Invalid receipt/result lineage is an integrity failure, not ordinary task
  failure.
- Output outside delegated scope is rejected and retained as security evidence;
  it is not promoted to a valid result.
- Originator acknowledgement is not required to establish completion, because
  Hermes owns terminal truth. Acknowledgement only closes result delivery.

## 15. Crash, retry, and replay behavior

| Failure boundary | Authoritative state / retry owner | Allowed replay | Forbidden side effect / terminal rule |
|---|---|---|---|
| Before delegation persistence | No delegation exists; originator may resubmit | Same request identity | No authorization or delivery may exist |
| Delegation persisted before lease issuance | Delegation is authoritative; Hermes resumes lower-layer authorization/route/lease sequence | Same delegation | Do not mint another delegation |
| Lease issued before mailbox delivery | Lease and lineage are authoritative; Hermes enqueues delivery | Same lease/message idempotency key | No second lease or launch |
| Delivery persisted before receiver read | `DELEGATION/PENDING`; receiver retries claim | Read same message | No duplicate message |
| Receiver reads, crashes before acceptance | Delivery claim expires; receipt absent; receiver may read same message | Same delivery | No `EXECUTING`; no new attempt automatically |
| Acceptance persisted before Codex invocation | Receipt is authoritative; adapter resumes exact launch admission | Same receipt and launch idempotency key | No second receipt or blind invocation |
| Codex starts, caller loses response | Launch state is unresolved; adapter reconciles exact runtime idempotency record | Lookup only until definitive | No second Codex process while unresolved |
| Codex completes, result not persisted | Adapter-owned durable output spool/runtime record is authoritative transport evidence; Hermes normalizes it | Re-read same captured output | No rerun solely because Hermes missed response |
| Result persisted, originator has no acknowledgement | Result and `RESULT_DELIVERY/PENDING` are authoritative; originator retries claim | Same result delivery | Never rerun delegated work for delivery |
| Duplicate originator submission | Existing delegation/hash wins | Exact replay returns existing delegation | Divergent same-key request conflicts |
| Duplicate mailbox delivery | Existing message/hash wins | Exact replay returns existing message | Divergent same-key payload conflicts |
| Duplicate receiver acceptance | Existing receipt/hash wins | Exact replay returns existing receipt | Divergent receipt is integrity failure |
| Duplicate Codex invocation attempt | Existing launch/runtime idempotency state wins | Lookup/reconcile only | Never spawn a second process for same launch key |
| Cancellation before acceptance | Cancellation event wins if committed first | Receiver re-reads and rejects/cancels | Acceptance cannot commit afterward |
| Cancellation after acceptance, before execution | Receipt remains; cancellation is authoritative | Receiver returns `CANCELLED` | No capability-bearing work may begin |
| Revocation before execution | Revocation event is authoritative | Receiver may only report rejection/cancellation | Lease cannot authorize work |
| Lease expiry before execution | Expired lease is authoritative | New work requires new authorization/attempt/lease | Existing lease cannot be renewed in place |
| Lease expiry during execution | Accepted attempt plus expiry event; receiver stops cooperatively | Return one cancellation result/evidence | No further tool/write calls; no `SUCCEEDED` promotion |
| Conflicting result for same attempt | First valid persisted result wins | Exact replay only | Second divergent result is integrity failure |
| Corrupted/tampered mailbox evidence | Hash/lineage validation fails; message is quarantined as evidence | No automatic replay from corrupted payload | Fail closed; do not acknowledge or advance projection |
| Hermes restart at any boundary | SQLite artifacts/events reconstruct projection | Resume the owning boundary | No inference from process absence or timestamps alone |
| Originator restart | Hermes mailbox retains verified result | Claim/ack same delivery | No duplicate execution |

Retries create a new `ExecutionAttempt` under the same `delegation_id`. They do
not create a new delegation unless the objective, input, scope, or target changes.
Automatic retry is off in the first implementation.

## 16. Duplicate prevention

The system must enforce:

- unique `(originator_agent_id, originator_request_id, delegation_revision)`;
- one canonical envelope hash per `delegation_id`;
- existing attempt-limit and atomic-claim invariants;
- one active route per attempt;
- one launch attempt per reservation;
- one receiver receipt per attempt;
- one terminal result per attempt;
- one idempotent result delivery per `(result_id, recipient_agent_id)`.

Exact replay returns the existing artifact. Same-key divergent content raises a
typed conflict and performs no external action.

## 17. Revocation and cancellation

- Before launch: revocation prevents claim, route, admission, or launch.
- After launch but before acceptance: Hermes records cancellation requested;
  receiver must reject if it has not accepted.
- After acceptance: cancellation is cooperative in the first version. The
  receiver returns `CANCELLED` with evidence of the last completed boundary.
- Expiry prevents new actions but does not erase already-recorded lineage.
- Force termination is not part of R11 design authority. A later adapter may
  support it under a separate, explicit capability and evidence contract.
- Cancellation never deletes artifacts, results, or audit events.

## 18. State ownership

| State | Authoritative owner |
|---|---|
| Task and delegation projection | Hermes governance store |
| Authorization, claim, attempt, route, launch, receipt, result lineage | Hermes execution authority store |
| Agent registry and descriptor snapshots | Hermes |
| Runtime process/session state | Receiving agent runtime |
| Transport idempotency acknowledgement | Adapter/receiver-owned registry, reconciled by Hermes |
| Output files | Declared output store; identity captured by Hermes hashes |
| Result delivery mailbox | Hermes |
| Agent private reasoning/context | Agent runtime; never authoritative |
| Obsidian/Anytype projection | Non-authoritative projection only |

Agents may propose records. Only Hermes validates and promotes them into
authoritative state.

R12 uses one Hermes SQLite authority database for the first seven Hermes-owned
rows above so local transactions can atomically bind an artifact and its mailbox
event. The existing adapter-owned launch idempotency registry remains a separate
transport store because the runtime boundary must be independently reconcilable.
That store is not governance authority and cannot project task state. No receiver
may write either store directly.

## 19. Security and trust boundaries

- Agent output is untrusted input.
- No agent may mint its own authorization or alter attempt limits.
- Prompt text cannot expand tools, filesystem paths, network access, or runtime.
- Secrets are references resolved by trusted adapters and never hashed into the
  envelope or logged in results.
- Receiver identity must be authenticated by the configured transport binding.
- Free-form shell commands are prohibited from runtime bindings.
- Result schemas, output size, event count, and log capture are bounded.
- All conflicts and integrity failures fail closed and append durable evidence.

## 20. Proposed R12 implementation sequence after approval

This packet authorizes none of these steps. Each requires a separate approval.

R12 is one CPU-only umbrella objective, but each sub-slice requires its own
explicit continuation authority and green gate:

1. R12A contracts: one delegation-domain module containing agent principal,
   delegated task, capability lease, receipt, result, result-delivery, and
   mailbox-message artifacts plus pure tests.
2. R12B persistence: one SQLite delegation/mailbox store with atomic,
   append-only, idempotent operations; no process launch.
3. R12C composition: one thin service binding the new artifacts to existing
   authorization/attempt/router/start mechanics with deterministic fake agents.
4. R12D Codex adapter qualification: dry-run argv/environment construction,
   pinned-binary verification, fake-process JSONL/schema/timeout/cancellation
   tests, and no live model invocation.
5. R12E one-shot proof: only under separate live-agent authorization, execute
   one harmless deterministic read-only fixture transformation and return it
   through the durable mailbox.

Kilo interface qualification follows R12 and remains a separate governance
slice. No R12 sub-slice enables scheduler-wide or generic agent delegation.

## 21. Proposed R12 acceptance tests

Before R12E can be considered, focused tests must demonstrate:

- canonical JSON vectors for Unicode escaping, nulls, booleans, integers,
  newline normalization, list ordering, map ordering, and forbidden floats;
- stable `delegation_id` and `task_input_hash`, plus changed-content same-key
  conflict and path-independent identity;
- complete identifier inequality and exact lineage binding through envelope,
  authorization, attempt, route, lease, launch, receipt, runtime, result, and
  result delivery;
- lease expiry/revocation/renewal and fail-closed verification;
- receipt uniqueness, rejection taxonomy, and cancellation/revocation races;
- append-only mailbox ordering, atomic artifact/message persistence, claim
  expiry, acknowledgment, duplicate replay, and divergent conflict;
- result schema/evidence validation and conflicting-result rejection;
- every crash/retry matrix row in Section 15 with no duplicate side effect;
- Codex adapter binary/version/hash pinning, trusted argv, stdin-only task data,
  bounded environment, read-only sandbox, JSONL parsing, final schema
  validation, exit-code handling, timeout, cancellation, and output spool
  recovery using a fake process, plus a model-visible-tool inspection proving
  the disabled capability set is absent;
- negative tests proving no GPU, ComfyUI, image pipeline, scheduler, generic
  shell/network, Kilo UI, authority-store bypass, or automatic retry capability.

The first live proof is not authorized by R11. When separately authorized under
R12E, it must demonstrate all of the following with a harmless text-only task:

- one registered originator and one registered receiver;
- one canonical delegation envelope and hash;
- one explicit authorization, claim, attempt, route, and launch attempt;
- receiver verifies and accepts the exact envelope;
- no work occurs outside the capability lease;
- one schema-valid result and evidence package;
- Hermes verifies lineage and marks completion;
- originator retrieves and acknowledges the same result;
- exact replay creates no new execution;
- divergent same-key replay fails closed;
- simulated lost launch acknowledgement reconciles without duplicate work;
- simulated originator restart still receives the durable result;
- no GPU, ComfyUI, browser automation, social posting, or image pipeline.

## 22. Explicit non-goals

- Regional Hand Repair implementation or another GPU pilot.
- Studio Bible or image-pipeline changes.
- Autonomous agent chains.
- Automatic retries.
- Dynamic agent self-registration.
- Agent-selected authority expansion.
- Kilo UI automation.
- General MCP orchestration before the delegation contract is proven.
- `app.py` integration.
- Production scheduler activation.

## 23. Review decisions

Frozen recommendations for review:

1. Preserve all generic EA-4A through EA-4E mechanics.
2. Demote RHR R8-R10 to qualification evidence only.
3. Add an agent acceptance gate before `EXECUTING` for delegated agent work.
4. Use a transport-neutral envelope with SQLite authoritative state.
5. Qualify `codex-cli-agent` as the first receiver through a local process
   adapter because it has a supported unattended interface.
6. Defer Kilo until a supported callable interface is demonstrated.
7. Require explicit approval before R12 implementation and before any live
   agent invocation.
8. Use one Hermes SQLite authority database for delegation/mailbox truth plus
   the existing separate adapter idempotency registry for transport recovery.
9. Persist receiver acceptance in its own immutable table and atomically append
   the corresponding mailbox event.
10. Treat the installed Codex CLI as a qualified future adapter only when its
    executable hash/version and trusted argv are pinned; do not depend on an
    undocumented Codex session event for Hermes runtime identity.

## 24. Final disposition

EA-4D.4F-R11 DESIGN REVIEW: ACCEPTED / FROZEN

AGENT-TO-AGENT OBJECTIVE: RESTORED

REGIONAL HAND REPAIR: QUALIFICATION EVIDENCE ONLY

STUDIO BIBLE / IMAGE PIPELINE: OUT OF SCOPE

IMPLEMENTATION: NOT AUTHORIZED

EA-4D.4F-R12 IMPLEMENTATION: NOT AUTHORIZED

LIVE AGENT INVOCATION: NOT AUTHORIZED

GPU / COMFYUI: OFF

COMMIT / PUSH: NO
