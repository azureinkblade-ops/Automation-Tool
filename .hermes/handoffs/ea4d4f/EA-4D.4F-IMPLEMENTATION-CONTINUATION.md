# EA-4D.4F Implementation Continuation

## Current state

- Repository: `C:\Users\David\Documents\Automation tool`
- Worktree: `.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- HEAD: `0fc8766f6ac879edb2161bd123752c68b7e4aa0d` (R8 committed)
- Completed: Steps 01-15, R8 source-closure Steps 17-20 (COMMITTED), R9 live-pilot identity freeze (Step 21)
- Current disposition: R8 CLOSED/COMMIT-BOUND; R9 live pilot packet FREEZE-READY (design only)
- Live GPU authority: NO
- Push authority: NO
- Commit: R8 committed @ `0fc8766f...`; R9 is design-only (no commit)

## Verified closure

- Step 11 authority integration: 7 passed
- Step 12 activation: 17 passed
- Step 13 recovery suites: 36 passed
- Regional Hand Repair with authority integration: 215 passed
- Same-launch-ID 4A through 4E proof: 7 passed
- Source-freeze guard: 3 passed
- Full `tests/hermes_core`: 1,021 passed, 32 subtests passed, 0 failed

## Relevant dirty scope

The exact proposed source/test inventory and hashes are in `source-freeze-manifest.json` (corrected to 44 files, including the two previously-omitted production-contract modules). Canonical completion notes are under this directory (`STEP-20-R8-source-closure-review-COMPLETE.md`, `R8-HOLD-RESOLUTION-COMPLETE.md`). Unrelated untracked image-pipeline files (`image_pipeline_v2_execution.py`, `image_pipeline_v2_provenance.py`) and pytest temporary directories are explicitly outside the freeze and remain untouched.

## Verified closure (R8 resolver, 2026-08-27)

- Manifest hash guard: 44 files, 0 mismatch, HASH-CLEAN (independent SHA-256 walk).
- RHR + authority integration: 215 passed.
- Four modified hermes_core tests (harness ownership): 81 passed.
- Freeze/hash guard detail: 3 passed.
- Complete `tests/hermes_core` discovery (66 files): 1,021 passed, 32 subtests passed, 0 failed.
- Transitive import closure: 0 leaks; 23 Hermes authority modules pulled in, all committed@HEAD `97f7603`.
- The 9 setup errors from the interrupted run were reproduced as caused by inaccessible pytest temporary storage and disappear under a repository-controlled temp root (test-temp override only).

## Next action

Step 20 closure blockers are RESOLVED. The corrected 44-file freeze is reproducible and all non-GPU gates pass. Clean commit is READY but NOT authorized in this slice:
- Authorize a SEPARATE clean commit of the 44-file closure on `feature/ea4f-regional-hand-repair-pilot` at HEAD `97f7603`.
- Only after that, separately authorize LIVE GPU PILOT if the pre-production workload is to be exercised on hardware.

Do not perform a live GPU/ComfyUI operation, stage, commit, push, or call `/free` without the appropriate later authorization.

## R9 Live Pilot Authorization Packet (2026-08-27, design/freeze only)

R9 was FREEZE-READY. R10 has now executed.

- Canonical pilot envelope (single source of truth): `STEP-21-live-pilot-identity-freeze.md`
- Packet: `EA-4D.4F-R9-LIVE-PILOT-AUTHORIZATION-PACKET.md`
- Frozen source image: `azink_main_004.png`, 768x1344 RGB opaque,
  sha256 `905e879a80e7f5b8de989174cb7a145e849964ccccee34cf9c24c48155f1c2d6`
- repair_execution_id: `v2repair-hand-f72d3aaf0ff63f62`
- task_input_sha256: `f72d3aaf0ff63f627863b922d8ec141467a64467cdb30747a0b02c770deafe8f`

## R10 Live GPU Pilot (2026-08-27, executed)

EA-4D.4F-R10 LIVE GPU PILOT: FAIL
GPU SUBMISSIONS: 1
TECHNICAL VERIFICATION: FAIL (V2 outside-mask pixel immutability)
SECOND GENERATION: NOT AUTHORIZED
CLEANUP: COMPLETE
PUSH: NO

- prompt_id: `9ad7bc2c-909f-4db1-90e3-911786bd1400`
- output_sha256: `097babb69cf7a166fef51675dc0ccd31ba5fd79a6ce4ec302e5a62ad302e8220`
- V0 PASS, V1 PASS, V2 FAIL, V3 PASS
- V2 diagnosis: global VAE round-trip quantization, not a mask-boundary violation
- runtime_binding_id: `rhr-binding-r10-001`, runtime_binding_hash `c8982508...`
- operator_approval_durable: true
- post-cleanup GPU: 2960 MiB used, 13086 MiB free, 53 C
- evidence: `.hermes/handoffs/ea4d4f/STEP-22-live-gpu-pilot-COMPLETE.md`
- result: `.hermes/handoffs/ea4d4f/EA-4D.4F-R10-LIVE-GPU-PILOT-RESULT.md`

Repository HEAD unchanged at `0fc8766f...`; no code edits, no push. Runtime
artifacts remain outside the repo at `C:\Users\David\AppData\Local\hermes\r10-pilot\`.

## 2026-08-27 Course correction - Agent-to-Agent integration restored

EA-4D.4F drifted from its governing objective after Regional Hand Repair was
promoted from a qualification workload into the roadmap. That promotion is
reversed.

Regional Hand Repair R8-R10 remains valid qualification evidence for the lower
Execution Authority mechanics. It is not the EA-4D.4F workload, does not govern
future slices, and is not a dependency of agent integration. The Studio Bible,
ComfyUI, and image pipeline remain Kilo-owned independent work and are outside
EA-4D.4F.

The next governance slice is now:

`EA-4D.4F-R11 - Agent-to-Agent Governed Delegation Integration`

R11 is design-only and freezes:

- named originator, authority, router, and receiving-agent identities;
- a canonical hash-bound delegated-task envelope;
- delegation identity separate from authorization, execution attempt, launch
  attempt, runtime run, and result identity;
- least-authority capability propagation without transferring Hermes authority;
- deterministic named-agent routing;
- receiver acceptance/rejection before agent work may project `EXECUTING`;
- status, terminal result, evidence, and result return to the originator;
- crash, replay, retry, cancellation, and duplicate-prevention semantics;
- Hermes versus agent state ownership;
- a transport-neutral contract with Codex CLI as the first proposed real
  receiver adapter and Kilo deferred until a supported unattended interface is
  proven.

Canonical packet:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R11-AGENT-TO-AGENT-GOVERNED-DELEGATION-DESIGN.md`

Authority state:

- R11 design: ACCEPTED / FROZEN.
- Agent integration implementation: NOT AUTHORIZED.
- Live agent invocation: NOT AUTHORIZED.
- Regional Hand Repair continuation: STOPPED.
- GPU / ComfyUI: OFF.
- Commit / push: NO.

## 2026-08-27 R11 design review and freeze complete

The R11 review accepted and froze the agent-to-agent governed delegation
contract. No production code, runtime state, GPU workflow, or agent process was
modified or invoked.

Frozen design SHA-256:
`79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`

Completion report:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R11-DESIGN-REVIEW-FREEZE-COMPLETE.md`

The accepted contract freezes canonical delegation identity and hashing,
least-authority capability leases, durable receiver acceptance, append-only
Hermes-owned mailbox delivery, deterministic result return, fail-closed replay
and cancellation behavior, and a gated R12A-R12E implementation sequence.

Next authority boundary:

- R12A domain-contract implementation requires separate authorization.
- R12B-R12E remain unauthorized until their preceding gate is accepted.
- A live Codex invocation requires separate R12E authorization after R12D proves
  that the adapter exposes no prohibited model-visible tools.
- Commit / push: NO.

## 2026-08-28 R12A delegation domain implementation complete

EA-4D.4F-R12A is `COMPLETE / NOT COMMITTED`.

R12A added only the canonical delegated-task domain and its durable SQLite
store, plus focused tests. The production surface remains exactly two new
modules:

- `tools/hermes_core/delegated_task.py`
- `tools/hermes_core/sqlite_delegation_store.py`

The SQLite schema is version 1. It durably stores delegations, capability
leases, delegation cancellations, and lease revocations with fail-closed
replay/conflict and reconstruction integrity checks.

Two implementation/test corrections were made during verification:

- all SQLite connections are now explicitly closed, fixing a Windows temporary
  database handle leak;
- four tamper fixtures now commit their deliberate corruption before the
  integrity reader is invoked.

Verification is green at current counts:

- R12A focused: 50 passed, 15 subtests passed;
- complete `tests/hermes_core/`: 1,071 passed, 47 subtests passed;
- all authorized intermediate EA-4D.4A-E, authority/attempt, worker-routing,
  launch, start-result, and migration gates passed with zero failures.

Completion report:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12A-DELEGATION-DOMAIN-IMPLEMENTATION-COMPLETE.md`

Authority boundary:

- R11 design: UNCHANGED / FROZEN.
- R12B: NOT AUTHORIZED.
- R12C-R12E: NOT AUTHORIZED.
- Live agent invocation: NOT AUTHORIZED.
- Commit: NOT AUTHORIZED.
- Push: NO.

## 2026-08-28 R12B delivery and receiver acceptance - COMMITTED

EA-4D.4F-R12B: COMPLETE / COMMITTED

- R12B commit SHA: `e7b42eac2931f20a400092b3b5fa8d7323557714`
- R12B parent SHA: `025bfe33a7229b044ba421469a7516166fffeda1` (R12A)
- Schema version: 2
- R12B focused: 38 passed, 25 subtests
- R12A focused: 50 passed, 15 subtests
- Full Hermes Core: 1109 passed, 72 subtests
- Prohibited-capability audit: CLEAR

## 2026-08-28 R12C delegation composition - COMMITTED

EA-4D.4F-R12C: COMPLETE / COMMITTED

- R12C commit SHA: `23023ae91dd6a464b985b1d171afd1aa0aca00b8`
- R12C parent SHA: `e7b42eac2931f20a400092b3b5fa8d7323557714` (R12B)
- R12C focused: 9 passed
- Full Hermes Core: 1,118 passed, 72 subtests
- Prohibited-capability audit: CLEAR

## 2026-08-29 R12D Codex adapter qualification - COMPLETE / NOT COMMITTED

The initial R12D implementation was placed on HOLD because it did not prove an
actual executable path/hash/version, bounded trusted cwd/environment, durable
replay, adapter cancellation behavior, strict structured-result validation, or
correct nonzero-after-start classification. Those defects have been remediated.

The previously frozen Codex executable disappeared during an application
update. A separate non-live compatibility review accepted and re-froze the
installed successor without changing frozen R11 architecture:

- Canonical path:
  `C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe`
- Version: `codex-cli 0.150.0-alpha.12.2`
- SHA-256: `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`
- Qualification:
  `.hermes/handoffs/ea4d4f/EA-4D.4F-CODEX-BINARY-REQUALIFICATION.md`

The repaired adapter now binds and verifies that exact executable, uses trusted
Windows-safe argv/cwd/environment, enforces a 5..300 second timeout, persists
schema-versioned transport idempotency before fake spawn, prevents blind replay,
observes durable cancellation/revocation, validates strict JSONL plus final
result schema, and preserves definitive process-start evidence independently
from terminal success.

Verification is green at the current final-focused counts:

- R12D focused: 64 passed;
- R12C focused: 9 passed;
- R12B focused: 38 passed, 25 subtests;
- R12A focused: 50 passed, 15 subtests;
- authority/attempt/routing/launch/start ladder: 548 passed;
- complete Hermes Core final rerun: 1,182 passed, 72 subtests.

Completion report:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12D-CODEX-ADAPTER-QUALIFICATION-IMPLEMENTATION-COMPLETE.md`

No `codex exec`, prompt, model workload, or agent task was launched. R12E
remains authorized for one live proof with zero definitive starts and one
invocation remaining.

## 2026-08-28 R12E-R1 Codex CLI compatibility remediation - HOLD / ARCHITECTURAL INCOMPATIBILITY

EA-4D.4F-R12E-R1: HOLD / ARCHITECTURAL INCOMPATIBILITY

**Failure preservation:**
- Original R12E invocation ID: `2878095abb0b500f5dc684eca7c8afe61f2f5e51d70442a7ce1c0c08477e5fe5`
- PID: 660
- Definitive starts: 1 (permanent)
- Exit code: 2
- Stderr: `error: unexpected argument '--ask-for-approval' found`
- Consumed budget: 1
- Terminal state: FAILED

**Root cause:**
- Prior binary requalification (commit 0fe869c) relied on help-surface inference
- The `--ask-for-approval` flag existed in alpha.8 but was removed in alpha.12.2
- No parser-only validation was performed to confirm argv acceptance
- The frozen R11 argv contract (Section 11.2) specifies `--ask-for-approval never` which is not valid in codex-cli 0.150.0-alpha.12.2

**Semantic equivalence analysis:**
- `--dangerously-bypass-approvals-and-sandbox` removes sandbox entirely (NOT equivalent)
- `--approve-for-me` uses workspace-write sandbox (NOT equivalent to read-only)
- No alpha.12.2 flag provides `approval policy = never` WITH `sandbox = read-only`
- SEMANTIC_EQUIVALENT_AVAILABLE=NO

**Classification:** Case B — Architectural change required

**Required governance action:** HOLD — Do not self-authorize redesign of approval semantics

Compatibility record: `.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R1-CODEX-CLI-COMPATIBILITY-REQUALIFICATION.md`

Authority boundary:

- R12A: COMPLETE / COMMITTED.
- R12B: COMPLETE / COMMITTED.
- R12C: COMPLETE / COMMITTED.
- R12D: COMPLETE / COMMITTED.
- R12E: FAIL / TERMINAL.
- R12E-R1: HOLD / ARCHITECTURAL INCOMPATIBILITY.
- Kilo / GPU / ComfyUI / Studio Bible / image pipeline: NO.
- Push: NO.

## 2026-08-29 R12E-R2 approval/sandbox redesign - DESIGN PASS

EA-4D.4F-R12E-R2 DESIGN: PASS / SEMANTIC EQUIVALENT FOUND

- The original R12E invocation remains terminal `FAILED`, PID 660, exit 2.
- Original authority remains consumed: authorized 1, definitive starts 1, remaining 0.
- The lingering `PREPARED` file is a preparation snapshot, not current execution truth.
- Durable transport/evidence state prevents reuse; a focused failed-terminal replay test was added.
- alpha.12.2 still supports `--ask-for-approval never`, but only as a top-level option before `exec`.
- The safe successor preserves `approval=never` plus `sandbox=read-only` and `--ignore-user-config`.
- `--approve-for-me` is rejected because it requires workspace-write.
- dangerous approval/sandbox bypass remains prohibited.
- R12D qualification must bind binary identity plus a complete CLI-contract identity.
- Production adapter correction is not authorized by this design gate.
- No new live proof, model task, GPU, ComfyUI, browser, scheduler, or Kilo action occurred.

Design record: `.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R2-CODEX-APPROVAL-SANDBOX-REDESIGN.md`

Next required gate: a narrowly scoped implementation authorization for the
reordered argv and CLI-contract qualification. A future live proof requires a
separate packet, new identities, and a new one-shot budget.

## 2026-08-29 R12E-R3 ordered argv and CLI contract - COMMITTED

EA-4D.4F-R12E-R3: PASS / COMMITTED

- Production argv now places `--ask-for-approval never --sandbox read-only` before `exec`.
- Adapter version is `1.1`.
- Qualified CLI contract ID is `21f341c1ac959ee3a7c7ce929baf492183bd0d07e7443c0e76e4f22f0196bc02`.
- Eligibility requires matching absolute binary path, SHA-256, version, contract ID, and exact flattened argv.
- Ambient user config remains disabled by the frozen `--ignore-user-config` exec option.
- Historical post-`exec` approval ordering now fails qualification before process capability.
- Non-live parser qualification passed against alpha.12.2 with no model/task output.
- Adapter qualification: 90 passed.
- Process controller: 4 passed.
- Result store: 16 passed, 6 subtests.
- R12C/R12B/R12A: 9; 38 + 25 subtests; 50 + 15 subtests.
- Authority/routing/launch/start/migration ladder: 303 / 85 / 33 / 116 / 11.
- EA-4D.4A-E: 28 / 25 / 11 / 11 / 19.
- Complete Hermes Core: 1,228 passed, 78 subtests, zero failures.
- Original R12E remains immutable `DEFINITELY_STARTED / FAILED`, PID 660, remaining 0.
- R12E-R3 live starts: 0.
- No Kilo, browser, MCP, network, scheduler, GPU, ComfyUI, image pipeline, or RHR action.

Completion record:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R3-CODEX-ORDERED-ARGV-IMPLEMENTATION-COMPLETE.md`

Next gate: `EA-4D.4F-R12E-R4 ONE-SHOT LIVE REQUALIFICATION`, separately
authorized with new identities and a new one-shot budget. R12E-R4 is not
authorized by R12E-R3.

## 2026-08-29 R12E-R4 one-shot live requalification - FAIL / TERMINAL

- New governed R12E-R4 identities and runtime state were created without reusing original R12E lineage.
- Pre-live focused qualification passed: 110 tests + 6 subtests.
- Binary, adapter, ordered CLI contract, read-only sandbox, approval `never`, and isolated config all matched the frozen preflight.
- Exactly one Codex process definitely started: PID `7196`; budget is consumed (`1/1`, remaining `0`).
- The CLI contract was accepted and Codex emitted `thread.started` and `turn.started`.
- The request then failed before model/task execution with `invalid_json_schema`: a const-only `evidence_type` property lacked an explicit `type` key.
- No structured result, result delivery, acknowledgement, or completion projection was created.
- Terminal exact replay used fake process capability, started zero processes, and divergent replay failed closed.
- Post-live complete Hermes Core regression passed: 1,228 tests + 78 subtests, zero failures.
- Original R12E evidence remains immutable and hash-unchanged.
- No retry, source remediation, production activation, scheduler, Kilo, GPU, ComfyUI, image-pipeline, or RHR action occurred.

Terminal evidence:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R4-ONE-SHOT-LIVE-REQUALIFICATION-COMPLETE.md`

Next boundary: a separately authorized non-live schema-contract remediation.
Any later live proof requires entirely new identities and a new explicit budget.

## 2026-08-29 R12E-R5 schema-contract remediation - PASS / NOT YET COMMITTED

- Exact R12E-R4 failed schema recovered; file SHA-256 remains `51548a83...`.
- Root cause confirmed: seven const-only properties lacked explicit matching types; the first live-reported path was `evidence_manifest.items.properties.evidence_type`.
- The empty-only `output_manifest` also received an explicit closed `items` schema.
- Logical result semantics remain unchanged under `hermes.delegation_result/v1`.
- New local schema policy: `codex-structured-output-schema/v1`.
- Qualified canonical schema hash: `b2d9872b...`.
- Schema qualification ID: `7b404540...`.
- New and `PREPARED` invocations fail closed on missing qualification, invalid schema, hash mismatch, or schema drift before process capability.
- Already-terminal historical replay remains readable and launches no process.
- The CLI has no safe schema-only service validation command; `exec --help` validates argv parsing only. No live-service acceptance is claimed by R12E-R5.
- Focused gates: schema 25; adapter 90; process 4; result 16 + 6 subtests; R12C 9; R12B 38 + 25 subtests; R12A 50 + 15 subtests.
- Complete Hermes Core: 1,253 passed + 78 subtests, zero failures.
- R12E-R5 live starts/model invocations: 0 / 0.
- Original R12E and R12E-R4 evidence hashes remain unchanged.

Completion record:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R5-SCHEMA-CONTRACT-REMEDIATION-COMPLETE.md`

Next proposed gate: `EA-4D.4F-R12E-R6 ONE-SHOT LIVE REQUALIFICATION`, requiring
new identities and a separate one-shot budget. It is not authorized by R12E-R5.

## 2026-08-30 R12E-R6 preflight - HOLD / NOT STARTED

- Required alpha.12.2 binary was absent after an automatic Codex update.
- Installed successor was alpha.7.1 at a different path and SHA-256.
- R12E-R6 stopped at binary identity before creating identities or runtime state.
- Live accounting remains authorized 1, definitive starts 0, remaining 1.

## 2026-08-30 R12E-R6A successor qualification - PASS / READY FOR COMMIT

- Successor: `codex-cli 0.151.0-alpha.7.1`.
- SHA-256: `3052f7887c10e97f6cfe4941353bd0763300c4907e49a8688958cb40d4159d89`.
- New CLI contract ID: `ae576aea601f46634e6ad0d66b9097f78f157d161fdcd2195be6ad6b0db16495`.
- Approval `never`, read-only sandbox, ordered global options, isolated user
  config, structured output, and stdin delivery remain parser-qualified.
- R5 schema hash `b2d9872b...` and qualification ID `7b404540...` remain
  unchanged; live eligibility binds them independently to the new binary and
  CLI contract.
- Adapter 92, schema 26, process 4, result 16 + 6 subtests, R12C 9, R12B 38 +
  25 subtests, R12A 50 + 15 subtests, authority/start subset 575 + 20 subtests.
- Complete Hermes Core: 1,256 passed + 78 subtests, zero failures.
- Codex task/model starts: 0. R12E-R6 identities: 0. Push: no.

Qualification record:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R6A-CODEX-BINARY-REQUALIFICATION.md`

Next boundary: a fresh R12E-R6 live authorization explicitly bound to the
successor path, SHA-256, version, CLI contract ID, schema hash, schema
qualification ID, and committed R6A HEAD. It is not authorized by R6A.

## 2026-08-30 R12E-R6 instance-schema preflight - HOLD / NOT STARTED

- The R5 schema hash `b2d9872b...` embeds R4 task and receiver-receipt hashes.
- Fresh R6 lineage would necessarily change both values and therefore the
  complete schema hash and qualification identity.
- Reusing R5 bytes would bind R6 output to R4 lineage, so preparation stopped
  before real identities, runtime state, process capability, or budget use.
- R6 accounting remains authorized 1, started 0, remaining 1.

## 2026-08-30 R12E-R6B instance-bound schema qualification - PASS / READY FOR COMMIT

- Structural policy version: `codex-result-structural-policy/v1`.
- Structural policy ID:
  `c1c789f1ceb2c56b324bb4b54f26cf10d83380d5bcb9629b20b6f54ec4470dd3`.
- Instance qualification version: `codex-instance-schema-qualification/v1`.
- Only canonical task-input and durable receiver-receipt hashes are accepted as
  typed instance parameters; all R5 structural/result strictness remains fixed.
- Same policy/different lineage produces the same policy ID but different
  schema hashes and qualification IDs.
- Historical/cross-instance schema reuse, drift, incomplete binding, and wrong
  binary/CLI/policy/lineage qualification fail before process capability.
- R6B 26 + 3 subtests; adapter 92; schema 26; process 4; result 16 + 6
  subtests; R12C 9; R12B 38 + 25 subtests; R12A 50 + 15 subtests.
- Authority/start subset 575 + 20 subtests; complete Hermes Core 1,282 + 81
  subtests, zero failures.
- Live starts/model invocations/real R6 identities: `0 / 0 / 0`. Push: no.

Completion record:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R6B-INSTANCE-BOUND-SCHEMA-QUALIFICATION-COMPLETE.md`

Next boundary: a fresh R12E-R6 live authorization bound to the committed R6B
HEAD, structural policy ID, successor binary/CLI identities, and instance
qualification version. It must create durable R6 identities before deriving
and freezing the instance schema, and remains unauthorized by R6B.

## 2026-08-30 R12E-R6 fresh live preflight - HOLD / NOT STARTED

- Repository, ancestry, frozen R11, successor binary, CLI contract, and R6B
  structural/instance qualification checks passed.
- The committed live harness still binds `RUNTIME` to the immutable historical
  `.hermes/runtime/ea4d4f/r12e` evidence directory.
- That directory contains the original R12E terminal evidence, and `prepare()`
  correctly refuses to reuse it. Fresh R6 identities cannot be isolated under
  the committed source without a new runtime namespace.
- No `prepare` or `execute` call was made. Real R6 identities, process starts,
  and model invocations remain `0 / 0 / 0`; the R6 budget remains `1`.
- Focused non-live preflight: 164 tests + 9 subtests, zero failures.

Evidence record:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R6-ONE-SHOT-LIVE-REQUALIFICATION-COMPLETE.md`

Next boundary: separately authorized non-live runtime-namespace remediation,
then commit/requalification and a fresh live authorization. Historical R12E
runtime/evidence must remain immutable. Live R6 execution is not authorized.

## 2026-08-30 R12E-R6C runtime namespace isolation - PASS / READY FOR COMMIT

- Added deterministic runtime contract `hermes-runtime-namespace/v1`.
- Fresh runtime ownership derives from a fixed governed proof identity and a
  canonical owner hash, never from a caller path, timestamp, delegation ID, or
  invocation ID.
- The R6 owner `ea4d4f-r12e-r6-one-shot` resolves to
  `.hermes/runtime/ea4d4f/proof-adb795668b3266a8d95572cc`.
- Ownership is frozen in an exclusively created `runtime-owner.json` manifest
  bound to the exact source SHA. Exact replay is idempotent; foreign, unknown,
  malformed, or source-drifted ownership fails closed.
- Original `r12e` and `r12e-r4` namespaces remain read-only and unchanged.
- R6 namespace reservation now precedes all durable identity creation; it does
  not itself grant authority or process capability.
- Tests: R6C 19 + 15 subtests; R6B/preflight group 183 + 24 subtests;
  R12A/B/C 97 + 40 subtests; authority/start/routing 548; complete Hermes Core
  1,301 + 96 subtests, zero failures.
- Real R6 identities, runtime path creation, Codex starts, and model invocations
  remain `0 / 0 / 0 / 0`; live budget remains `1`.

Completion record:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R6C-RUNTIME-NAMESPACE-ISOLATION-COMPLETE.md`

Next boundary: fresh R12E-R6 live authorization bound to the committed R6C
HEAD, namespace contract, binary/CLI identities, and R6B schema contracts. It
is not authorized by R6C.

## 2026-08-31 R12E-R6 fresh live preflight - HOLD / NOT STARTED

- Repository, ancestry, frozen R11, R6C namespace identity, and clean-state
  checks passed at committed HEAD `e00780bb16ee13f3bad18501b9cc29d96f8b5f16`.
- Current UTC was `2026-08-31T13:11:30.5693520Z`; the committed harness deadline
  remained `2026-08-30T23:59:59Z`.
- The required `LEASE_EXPIRED=NO` gate therefore failed before namespace
  reservation or identity creation.
- Fresh namespace/owner manifest, real R6 identities, process starts, and model
  invocations remain `0 / 0 / 0 / 0`; live budget remains `1`.
- No deadline patch, binary requalification, source change, or live retry was
  attempted under the live packet.

The canonical R6 live evidence record was appended without removing the prior
runtime-collision HOLD. Next boundary: separately authorized non-live
time-window remediation, commit/requalification, then a new live authorization.

Authority boundary:

- R11 design: UNCHANGED / FROZEN.
- Binary successor: PASS / RE-FROZEN.
- R12D: COMPLETE / NOT COMMITTED.
- R12E: NOT STARTED.
- Kilo / GPU / ComfyUI / Studio Bible / image pipeline: NO.
- Push: NO.
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12B-DELIVERY-ACCEPTANCE-IMPLEMENTATION-COMPLETE.md`

Authority boundary:

- R12A: COMPLETE / COMMITTED.
- R12B: COMPLETE / NOT COMMITTED.
- R12C: NEXT PROPOSED GATE / NOT AUTHORIZED.
- R12D-R12E: NOT AUTHORIZED.
- Agent invocation / `EXECUTING` projection / GPU / ComfyUI: NO.
- Commit: NOT AUTHORIZED.
- Push: NO.

## 2026-08-31 R12E-R6D deterministic lease-window remediation - PASS / COMMIT HOLD

- Root cause confirmed in `run_r12e_live_proof.py`: a reusable fixed
  `2026-08-30T23:59:59Z` deadline was hashed through the authorization,
  delegation, lease, route, attempt, and mailbox material.
- Added policy `hermes-live-proof-lease-window/v1`, ID
  `63ab96fe12a3206d7ff7f5281b6c0765c9630e394f7c6b3743bce49409a2bc31`.
- The policy uses a finite 300-second UTC window, exact-expiry rejection, zero
  skew, no environment override, and no automatic renewal.
- A future fresh preparation exclusively writes `lease-window.json` after
  namespace reservation. Resume/refreeze/execute reload the same timestamps;
  replay cannot extend authority. Execute rechecks validity immediately before
  process-controller construction.
- Historical expired-fixture and fresh fake-attempt regressions pass. R6D
  focused: 24 + 8 subtests; R6C/R6D: 43 + 23; R6B: 26 + 3; R12A/B/C: 97 + 40;
  authority/start/routing: 548.
- Complete Hermes Core: 1,322 passed + 104 subtests, with 3 failures caused only
  by the separately pinned `6ca77c.../codex.exe` path disappearing after an
  automatic Codex update. Current `b99306.../codex.exe` has unqualified SHA-256
  `bfd4c3b...`.
- R6D did not requalify or invoke the replacement binary. Because the packet
  requires zero failures before commit, R6D remains uncommitted pending a
  separately authorized non-live binary requalification and clean rerun.
- Real R6 namespace/identities, Codex starts, and model invocations remain
  `0 / 0 / 0 / 0`; live budget remains `1`.

Completion record:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R6D-DETERMINISTIC-LEASE-WINDOW-REMEDIATION-COMPLETE.md`

Next boundary: non-live successor binary requalification is required and is
not authorized by R6D. Fresh R6 live preparation remains unauthorized.

## 2026-08-31 R12E-R6E successor binary requalification - PASS / READY FOR COMMIT

- The missing R6A `alpha.7.1` executable remains historical and was not
  rebound or rewritten.
- Qualified replacement: `b99306303521e97e/codex.exe`, `codex-cli
  0.151.0-alpha.7.2`, 313790256 bytes, SHA-256 `bfd4c3b971477a559eadaeae8b1e41382ccb7656bd0104970cf5c6c581f2da7d`.
- Replacement CLI contract ID:
  `98cc8fd6a6ffc1bb0bb4a675d5988cc8f4c31960ada4357003980b5d8befec5b`.
- Version/help and complete ordered parser-only qualification passed with no
  task output, model call, or agent task start. All dangerous approval/sandbox,
  config, unknown-binary, and drift cases remain fail-closed.
- The original three binary-pin failures now pass 3/3; adapter 92; R6D 24 + 8;
  R6C/R6D 43 + 23; R6B 26 + 3; R12A/B/C 97 + 40;
  authority/start/routing 548; complete Hermes Core 1,325 + 104, zero failures.
- Post-suite path/version/SHA/CLI identity recheck passed without drift.
- R6D policy ID remains `63ab96fe12a3206d7ff7f5281b6c0765c9630e394f7c6b3743bce49409a2bc31`;
  TTL remains 300 seconds.
- Real R6 namespace/identities, task/model starts remain `0 / 0 / 0 / 0`;
  live budget remains `1`.

Qualification record:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R6E-CODEX-BINARY-REQUALIFICATION.md`

R6D/R6E are eligible for the authorized exact-path clean commit. Fresh R6 live
execution remains unauthorized.

## 2026-08-31 R12E-R6 fresh live proof - FAIL / TERMINAL

- Source/binary/CLI/R11/namespace/lease/instance-schema prechecks passed at
  committed HEAD `4d8631fae5b17c3c2a84fea65ff63a8e0d579752`.
- A fresh 300-second lease was issued for `2026-08-31T14:21:30Z` through
  `2026-08-31T14:26:30Z`; namespace
  `proof-adb795668b3266a8d95572cc` and fresh R6 identities were created.
- Exactly one governed Codex task started as PID `9432`. CLI and live schema
  acceptance passed; model execution returned exit `0` with a parsed,
  schema-valid, lineage-valid, evidence-valid, output-scope-valid result.
- Hermes then failed in post-launch start-result persistence because the fresh
  schema-version-2 `execution_start_results` table lacks
  `runtime_binding_id`, although the persistence code requires it.
- Canonical result, result delivery, originator acknowledgement, COMPLETED
  projection, and post-result replay were not reached. No second process or
  retry occurred. R6 accounting is `STARTED=1 / REMAINING=0`.
- Post-live gates remain green: R6D 24+8; R6C/R6D 43+23; R6B 26+3; adapter 92;
  R12A/B/C 97+40; authority/start/routing 548; complete Hermes Core 1325+104.
- Historical original and R4 evidence hashes remain unchanged. Runtime evidence
  is preserved under the ignored isolated R6 namespace.

Canonical evidence:
`.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R6-ONE-SHOT-LIVE-REQUALIFICATION-COMPLETE.md`.

Next boundary: separately authorized non-live start-store schema
creation/migration remediation. Do not repair and rerun this consumed live
attempt. A future live proof requires new authority and fresh identities.

`EA-4D.4F-R12E-R6: FAIL / TERMINAL`

`PUSH: NO`


## 2026-08-28 R12E-R6F start-store schema compatibility remediation - PASS / COMMITTED

EA-4D.4F-R12E-R6F: PASS / COMMITTED

- R6F commit SHA: `8c84b700b343952d799ea71047622753c5d176a1`
- R6F parent SHA: `f712266bf4c81a09f9fd01df9f8985a4edfb2d32`
- Frozen R11 design SHA: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`

LIVE PROOF RESULT:
- Definitive starts: 1 (budget consumed)
- Remaining: 0
- PID: 9432
- Exit code: 2
- Failure boundary: POST-LAUNCH START-STORE SCHEMA COMPATIBILITY
- Original SQLite error: `sqlite3.OperationalError: no such column: runtime_binding_id`

REMEDIATION RESULT:
- R6F focused: 10 passed
- StartResult persistence: 39 passed
- Start-store migration: 11 passed
- Full Hermes Core: 1,335 passed, 104 subtests, 0 failures
- Prohibited-capability audit: CLEAR
- Singleton-enforced schema_version table
- Idempotent bootstrap with concurrent-thread safety
- Lenient schema version reads (accepts both old and new shapes)
- Migration idempotency (returns early if already at target version)
- No live Codex process
- No Codex process has been invoked
- No EXECUTING projection
- Live invocation budget remaining: 0
- Durable preflight state: PREPARED (transport registry), PID: none, definitive starts: 0

Authority boundary:

- R11 design: UNCHANGED / FROZEN.
- Binary successor: PASS / RE-FROZEN.
- R12D: COMPLETE / COMMITTED.
- R12E: FAIL / TERMINAL.
- R12E-R6F: PASS / COMMITTED.
- Kilo / GPU / ComfyUI / Studio Bible / image pipeline: NO.
- Push: NO.


## 2026-08-31 R12E-R7 successor live validation - FAIL / TERMINAL

EA-4D.4F-R12E-R7: FAIL / TERMINAL

- R7 authorized definitive starts: 1
- R7 definitive starts: 1
- R7 remaining: 0
- R7 PID: 44124
- R7 exit code: 1
- R7 failure: CODEX USAGE LIMIT (INFRASTRUCTURE)
- R7 process controller: PASS
- R7 start store: V3 QUALIFIED
- R7 binary: VERIFIED
- R7 CLI contract: VERIFIED
- R7 post-live regression: 74 passed
- R7 evidence: `.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R7-SUCCESSOR-LIVE-VALIDATION-COMPLETE.md`

Authority boundary:

- R11 design: UNCHANGED / FROZEN.
- Binary successor: PASS / RE-FROZEN.
- R12D: COMPLETE / COMMITTED.
- R12E: FAIL / TERMINAL.
- R12E-R6F: PASS / COMMITTED.
- R12E-R7: FAIL / TERMINAL.
- Kilo / GPU / ComfyUI / Studio Bible / image pipeline: NO.
- Push: NO.


## 2026-08-31 R12E-R8 successor live validation - PASS / LIVE QUALIFIED

EA-4D.4F-R12E-R8: PASS / LIVE QUALIFIED

- R8 authorized definitive starts: 1
- R8 definitive starts: 1
- R8 remaining: 0
- R8 PID: 41172
- R8 exit code: 0
- R8 outcome: SUCCEEDED
- R8 process controller: PASS
- R8 start store: V3 QUALIFIED
- R8 binary: VERIFIED
- R8 CLI contract: VERIFIED
- R8 model execution: PASS
- R8 StartResult persistence: PASS
- R8 durable result return: PASS
- R8 result delivery: PASS
- R8 originator ACK: PASS
- R8 COMPLETED projection: PASS
- R8 post-live regression: 74 passed
- R8 evidence: `.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R8-SUCCESSOR-LIVE-VALIDATION-COMPLETE.md`

Authority boundary:

- R11 design: UNCHANGED / FROZEN.
- Binary successor: PASS / RE-FROZEN.
- R12D: COMPLETE / COMMITTED.
- R12E: FAIL / TERMINAL.
- R12E-R6F: PASS / COMMITTED.
- R12E-R7: FAIL / TERMINAL.
- R12E-R8: PASS / LIVE QUALIFIED.
- Kilo / GPU / ComfyUI / Studio Bible / image pipeline: NO.
- Push: NO.
