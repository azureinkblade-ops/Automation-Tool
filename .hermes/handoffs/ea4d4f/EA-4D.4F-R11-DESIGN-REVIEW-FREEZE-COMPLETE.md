# EA-4D.4F-R11 Design Review / Freeze Complete

Date: 2026-08-27

Status: ACCEPTED / FROZEN

R12 implementation authority: NO

Live agent invocation: NO

GPU / ComfyUI: OFF

Commit / push: NO

## Precheck

- Repository/worktree:
  `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- HEAD: `0fc8766f6ac879edb2161bd123752c68b7e4aa0d`
- Parent: `97f7603c39c128fdd566a4b031c47689f779d193`
- Tracked modifications: none
- Known protected untracked state: `.hermes/handoffs/ea4d4f/`, pytest
  scratch directories, R6 governance files, and independent image-pipeline WIP
- Required R11 packet and all three supporting Obsidian artifacts: present

No anchor discrepancy required HOLD. Known untracked work was not staged,
deleted, or modified outside the R11 documentation set.

## Controlling design

`EA-4D.4F-R11-AGENT-TO-AGENT-GOVERNED-DELEGATION-DESIGN.md`

Frozen SHA-256:
`79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`

## Design review findings

The existing design had the correct system boundary and no architecture
blocker, but four areas were not exact enough for implementation:

1. Canonical JSON, optional values, list ordering, numeric rules, timestamp
   identity, path-independent identity, and hash relationships needed one
   normative contract.
2. The capability lease needed exact identity, ordering after named routing,
   renewal, expiry, revocation, and mid-execution behavior.
3. Receiver acceptance needed its own durable table and transaction boundary;
   a mailbox event alone was not a sufficient execution gate.
4. The mailbox needed exact message identity, ordering, append-only delivery
   events, replay, acknowledgement, retention, and SQLite boundaries.

Codex CLI provides a sufficiently stable future adapter surface when its binary
and version are pinned. Its help surface does not by itself prove all tool
capabilities are disabled, so R12D contains a mandatory model-visible-tool
inspection gate. Prompt instructions are not accepted as a security boundary.

## Exact amendments made

- Reused the existing Hermes canonical JSON/SHA-256 helpers.
- Forbade floats, NaN/infinity, omitted schema fields, absolute host paths,
  secrets, and non-canonical list/map forms.
- Defined deterministic `delegation_id` and content-only `task_input_hash`.
- Bound existing authorization/attempt/launch `input_hash` to the full delegated
  envelope artifact hash.
- Moved receiver-bound lease issuance after attempt and named route selection.
- Defined immutable lease identity and separate revocation/cancellation events.
- Added a first-class immutable `delegation_receipts` table and atomic receipt
  mailbox event.
- Froze rejection reason codes and acceptance race ordering.
- Froze one Hermes SQLite authority database for delegation/mailbox state, with
  the existing adapter-owned idempotency registry remaining transport-only.
- Defined append-only mailbox messages and hash-linked delivery events.
- Pinned the reviewed Codex executable, version, SHA-256, and future argv shape.
- Required a no-tool capability inspection before Codex receiver qualification.
- Expanded the crash/retry matrix to every required boundary.
- Reframed R12 as gated R12A-R12E sub-slices, with live invocation separately
  authorized only at R12E.

## Frozen DelegatedTaskEnvelope contract

- Artifact: `hermes.delegated_task`, version `1`.
- Canonical form: lexicographically sorted JSON keys, compact separators,
  `ensure_ascii=True`, then UTF-8 bytes.
- Optional fields: explicit JSON `null`.
- Integers: canonical base-10; floats forbidden; booleans are JSON booleans.
- Text: NFC, LF line endings, no silently trimmed trailing whitespace.
- Set-like lists: deduplicated and sorted; ordered lists use contiguous ordinals.
- Timestamps: UTC RFC3339 whole seconds ending in `Z`.
- Paths: content-addressed URI or workspace-relative POSIX path; no host root,
  drive, username, symlink-dependent identity, or traversal segments.
- Hash: lowercase SHA-256.
- `delegation_id`: `delegation-` plus SHA-256 of artifact type/version,
  originator agent id, originator request id, and non-negative revision.
- `task_input_hash`: content-only operation/objective/instructions/input and
  expected output/evidence contract; no target, runtime, worker, authority,
  scope, timestamp, or execution identity.
- Envelope artifact hash: every envelope field except the hash itself.
- Existing execution `input_hash` fields bind the full envelope artifact hash.

Timestamps are integrity-bearing envelope metadata but do not derive the
delegation id or task-input hash.

## Frozen capability-lease contract

- Artifact: `hermes.delegated_capability_lease`, version `1`.
- Issuer: `hermes-execution-authority`.
- Recipient: exact routed agent id and worker descriptor hash.
- Binding: delegation/envelope, authorization, attempt, route, operation,
  tools, paths, network policy, runtime, result schema, evidence, and expiry.
- Redelegation: false.
- Identity: `lease-` plus full SHA-256 of the canonical lease preimage.
- One lease per attempt/route pair; exact replay returns existing state and
  divergent replay conflicts.
- Renewal: only before acceptance and only as a new authorization, attempt,
  route, and lease identity.
- Revocation/cancellation: separate immutable Hermes events.
- Failure to verify: fail closed.
- Expired/revoked before acceptance: receiver rejects.
- Expired/revoked during execution: stop at the next safe cooperative boundary,
  perform no further delegated capability use, and return cancellation evidence;
  never promote a success result.

Hermes authority is never transferred.

## Frozen receiver-acceptance contract

- Artifact: `hermes.delegation_receipt`, version `1`.
- Identity: `receipt-` plus full SHA-256 of the canonical receipt preimage.
- Unique key: one receipt per `attempt_id`.
- Required lineage: envelope, lease, authorization, attempt, route, launch,
  receiver descriptor, runtime run, implementation, and version.
- Outcome: `ACCEPTED` or `REJECTED` with frozen rejection taxonomy.
- Persistence: own immutable table plus a hash-linked mailbox event in the same
  SQLite transaction.
- Replay: exact receipt returns existing; divergent receipt is integrity failure.
- Cancellation/revocation race: SQLite commit order controls. Cancellation first
  blocks acceptance; acceptance first moves later cancellation to cooperative
  execution handling.

Hermes may project agent work to `EXECUTING` only after definitive runtime start,
durable accepted receipt, and complete exact lineage validation.

## Frozen mailbox contract

- One Hermes SQLite authority database for authoritative delegation/mailbox
  artifacts.
- Messages are append-only and ordered by a monotonic sequence per recipient
  mailbox.
- Message identity is deterministic from mailbox id and idempotency key.
- Message types cover delegation, receipt, progress, result, cancellation,
  revocation, and result delivery.
- Same-key exact payload replay returns existing; divergent payload conflicts.
- Delivery state is derived from append-only hash-linked delivery events:
  `PENDING`, `CLAIMED`, `ACKNOWLEDGED`, or `DEAD_LETTER`.
- Claims expire and permit re-reading the same message, never creating a new one.
- Acknowledgement binds message id/hash, recipient, claim token, and time.
- Artifact and corresponding mailbox message are committed atomically.
- External process invocation remains outside the database transaction and uses
  existing launch idempotency/reconciliation.
- Retention is indefinite for R12; compaction is out of scope.
- Receivers cannot write Hermes authority or mailbox stores directly.

## Codex machine-interface findings

- Executable:
  `C:\Users\David\AppData\Local\OpenAI\Codex\bin\d0097be4feba73d0\codex.exe`
- Version: `codex-cli 0.150.0-alpha.8`
- SHA-256:
  `09d6723925e724edf0bbbbc7b9e204526e0fb1462c86bd2a4997311fd5071eba`
- Non-interactive entrypoint: `codex exec`.
- Input: prompt/canonical request through stdin using `-`.
- Output: JSONL events on stdout plus final output constrained by
  `--output-schema`; stderr is separate diagnostic evidence.
- Working directory: explicit `--cd`.
- State: `--ephemeral` for the proof.
- Config/rules: ignored for deterministic binding; authentication still comes
  from `CODEX_HOME` without exposing credentials.
- Sandbox: read-only.
- Tools: shell, browser, computer use, images, apps, plugins, hooks, and
  multi-agent features must be explicitly disabled and then mechanically
  inspected as absent.
- Timeout/cancellation: adapter-owned process handle with bounded terminate/kill;
  no reviewed native per-command CLI contract.
- Exit code: transport signal only; not proof of task success.
- Hermes runtime id: generated/persisted by the adapter before spawn. Any Codex
  thread id is optional metadata, not authoritative identity.

The CLI is acceptable for future qualification. A changed binary/version or
failure to prove the no-tool surface places R12D on HOLD.

## Exact identity relationships

`delegation_id`, `authorization_id`, `claim_id`, `attempt_id`, `route_id`,
`lease_id`, `launch_attempt_id`, `runtime_run_id`, `receipt_id`, `result_id`,
and `result_delivery_id` are distinct and non-substitutable.

- One task may own multiple delegations.
- One delegation may have multiple policy-authorized attempts.
- One attempt has at most one active route, lease, receipt, launch, runtime run,
  and terminal result.
- One verified result has one idempotent delivery per recipient.

## Crash/retry conclusion

The controlling design now covers all requested boundaries: delegation/lease/
delivery/receipt/invocation/result/acknowledgement loss, every duplicate replay,
cancellation and revocation races, lease expiry before/during work, conflicting
results, tampered mailbox evidence, and Hermes/originator restart.

At every boundary, SQLite artifacts/events define truth. The owner retries the
same identity. Unknown launch state reconciles before action. Automatic retries
remain off. No delivery failure may cause delegated work to rerun.

## Cancellation and revocation

- Before acceptance: cancellation/revocation blocks acceptance and execution.
- After acceptance: cooperative cancellation only in the first proof.
- The receiver must stop before the next capability use and return cancellation
  evidence.
- Force termination is not granted by R11.
- Cancellation never deletes evidence or rewrites immutable artifacts.

## Security and negative capabilities

R11/R12 do not grant GPU, ComfyUI, image generation, Studio Bible, Regional Hand
Repair, scheduler activation, background scanning, generic shell/network,
generic agent-to-any-agent execution, Kilo UI automation, automatic retry,
authority transfer, receiver authority-store writes, or routing bypass.

All agent output is untrusted until Hermes validates schema, hashes, lineage,
scope, identity, and evidence.

## Proposed R12 mechanics surface

- R12A: one delegation-domain module and pure contract tests.
- R12B: one SQLite delegation/mailbox store; no process launch.
- R12C: one thin orchestration service using existing EA-4A-E mechanics and fake
  originator/receiver adapters.
- R12D: one Codex adapter with dry-run and fake-process qualification only.
- R12E: one separately authorized harmless deterministic text proof.

No broad refactor, scheduler integration, `app.py`, GPU, image pipeline, or Kilo
adapter belongs in R12.

## Proposed R12 acceptance tests

The exact test groups are frozen in Section 21 of the controlling design:
canonicalization/identity vectors; lineage inequality; lease lifecycle; receipt
and races; mailbox ordering/claims/ack/replay; result verification; all crash
matrix rows; pinned Codex adapter and fake-process behavior; and negative
capability proofs. R12E additionally proves exact replay, lost acknowledgement
recovery, originator restart delivery, and zero duplicate execution.

## Unresolved blockers

No blocker prevents R11 design freeze.

R12D has one explicit qualification gate: prove the pinned Codex invocation has
no model-visible execution/browser/image/plugin tools. Failure places R12D on
HOLD and requires a stronger external sandbox or a different receiver adapter.

## Verification performed

- Repository/worktree/branch/HEAD/parent inspection: PASS.
- Required artifact existence: 4/4 PASS.
- Unexpected tracked modifications: 0.
- Read-only authority/attempt/route/start/runtime-binding code inspection: PASS.
- Codex version/help/features inspection: PASS; no agent task invoked.
- Codex binary SHA-256 inspection: PASS.
- Frozen-design structural assertions: 7/7 PASS.
- Production tests: not run; this slice changed documentation only.

## Final authority state

EA-4D.4F-R11: ACCEPTED / FROZEN

EA-4D.4F-R12 IMPLEMENTATION: NOT AUTHORIZED

LIVE AGENT INVOCATION: NOT AUTHORIZED

COMMIT: NOT AUTHORIZED

PUSH: NO

GPU / COMFYUI: OFF

STUDIO BIBLE / IMAGE PIPELINE: OUT OF SCOPE

REGIONAL HAND REPAIR: QUALIFICATION EVIDENCE ONLY

KILO: DEFERRED

Next permitted action: request and receive separate authority for R12A contracts
and pure tests only.
