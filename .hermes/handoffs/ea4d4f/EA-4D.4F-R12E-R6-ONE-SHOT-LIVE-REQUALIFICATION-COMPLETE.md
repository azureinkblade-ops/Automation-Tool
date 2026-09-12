# EA-4D.4F-R12E-R6 One-Shot Live Requalification

## Disposition

`EA-4D.4F-R12E-R6: HOLD / NOT STARTED`

The fresh live attempt stopped at the pre-live runtime-isolation gate. No real
R6 identity was created and no Codex task process was exposed or started.

## Governing Source

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- HEAD: `91a70d46cfa2538720a9c88fce17d0fab3d004ba`
- Parent: `be8e1101b233a087b3f2192bf54d7d2867468055`
- Tracked modifications: `0`
- Staged paths: `0`
- Unrelated untracked paths: `139`, preserved
- Merge/rebase/cherry-pick state: none
- Frozen R11 SHA-256:
  `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`

## Runtime Qualification

- Executable:
  `C:\Users\David\AppData\Local\OpenAI\Codex\bin\6ca77c4a9caa4eed\codex.exe`
- Version: `codex-cli 0.151.0-alpha.7.1`
- Binary SHA-256:
  `3052f7887c10e97f6cfe4941353bd0763300c4907e49a8688958cb40d4159d89`
- CLI contract ID:
  `ae576aea601f46634e6ad0d66b9097f78f157d161fdcd2195be6ad6b0db16495`
- Structural policy ID:
  `c1c789f1ceb2c56b324bb4b54f26cf10d83380d5bcb9629b20b6f54ec4470dd3`
- Instance qualification version:
  `codex-instance-schema-qualification/v1`

All required repository, binary, CLI, structural-policy, ancestry, and frozen
R11 checks passed.

## Pre-Live Blocker

Committed `tests/hermes_core/run_r12e_live_proof.py` still defines:

`RUNTIME = ROOT / ".hermes" / "runtime" / "ea4d4f" / "r12e"`

That directory is the immutable historical original-R12E evidence location.
It contains nine retained items, including `live-proof-evidence.json` with
SHA-256:

`67758d5c5843d8f9a0ffb7fc324e3297244c5af7496bbe3b773817091b380f62`

The harness correctly rejects preparation when that evidence exists:

`R12E evidence already exists; live proof cannot be prepared again`

Therefore the committed source cannot create a fresh isolated R6 durable
identity set without either reusing/overwriting historical R12E state or
changing the source/runtime binding. Both are prohibited by this live packet.
The harness was not invoked in `prepare` or `execute` mode.

Historical R12E-R4 evidence also remains unchanged at:

`6bc7af15e81f29a4545dc5557608801a4fa87a2ed6733367012f554a0b59eb0a`

## Non-Live Verification

- R6B instance-schema, historical schema, adapter, process-controller, and
  result-store surface: `164 passed, 9 subtests passed`
- Binary identity: pass
- CLI contract: pass
- Structural policy: pass
- Cross-delegation schema defense: pass
- Source binding: pass
- Fresh runtime isolation: **fail / source remediation required**

## Live Accounting

- Original R12E: authorized `1`, started `1`, remaining `0`
- R12E-R4: authorized `1`, started `1`, remaining `0`
- Current R12E-R6: authorized `1`, started `0`, remaining `1`
- Fresh R6 identities created: `0`
- R6 instance schema derived: no
- R6 process starts: `0`
- Model invocations: `0`
- PID: none
- Live budget consumed: no

## Required Next Boundary

A separate non-live remediation authorization must bind the fresh R6 harness to
a new deterministic runtime/evidence namespace while preserving the historical
`r12e` and `r12e-r4` directories byte-for-byte. It must add regression coverage
proving that fresh attempts cannot alias historical runtime state. After that
repair is committed and requalified, a new live R6 authorization is required.

No retry, source repair, runtime move, historical cleanup, process start, or
push is authorized by this record.

`R12E-R6_STATE=HOLD / NOT STARTED`

`DEFINITIVE_STARTS=0`

`REMAINING=1`

`LIVE CODEX START=NOT PERFORMED`

## 2026-08-31 Fresh Live Preflight Hold

`EA-4D.4F-R12E-R6: HOLD / NOT STARTED`

The renewed live packet was correctly bound to committed R6C source, but the
first time-sensitive authority check failed before namespace reservation.

- Preflight UTC: `2026-08-31T13:11:30.5693520Z`
- Committed harness deadline: `2026-08-30T23:59:59Z`
- Lease state: expired
- Required packet state: `LEASE_EXPIRED=NO`
- Governing HEAD: `e00780bb16ee13f3bad18501b9cc29d96f8b5f16`
- Parent: `627d297f9da3399df3facf562fce6a42952f66a5`
- Frozen R11 SHA-256:
  `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- Tracked modifications/staged paths: `0 / 0`
- Unrelated untracked paths: `139`, preserved

The isolated R6 namespace
`.hermes/runtime/ea4d4f/proof-adb795668b3266a8d95572cc` was not created.
No owner manifest, delegation, lease, mailbox message, receipt, authorization,
claim, execution attempt, launch attempt, invocation, instance schema, or
transport state was created. No binary auto-requalification or live process
qualification was attempted after the expired-lease gate failed.

Live accounting remains:

- Authorized definitive starts: `1`
- Definitive starts: `0`
- Remaining: `1`
- PID: none
- Codex task process starts: `0`
- Model invocations: `0`

Required next boundary: separately authorized non-live time-window remediation
that replaces the expired fixed deadline with a fresh, deterministic,
governance-bound validity window without weakening lease-expiry enforcement.
That repair must be committed and requalified before a new live authorization.

`RUNTIME_NAMESPACE_CREATED=NO`

`R6_IDENTITIES_CREATED=0`

`LIVE_BUDGET_CONSUMED=NO`

## 2026-08-31 Fresh One-Shot Live Attempt - FAIL / TERMINAL

`EA-4D.4F-R12E-R6: FAIL / TERMINAL`

The fresh governed Codex task started exactly once and returned a valid,
schema-constrained result. The attempt then failed in Hermes post-launch
reconciliation before canonical delegation-result persistence. No retry was
performed or is authorized.

### Source And Qualification Binding

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- HEAD: `4d8631fae5b17c3c2a84fea65ff63a8e0d579752`
- Parent: `6646b39946988afe61500ce32a4fe203b8808c19`
- Frozen R11 SHA-256: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- Tracked modifications / staged paths before preparation: `0 / 0`
- Unrelated untracked paths: `139`, preserved
- Merge/rebase/cherry-pick state: none
- Preflight SHA-256: `a1be599ee9490e2b6a8b9612214cd3bc745a4f0c8a3c209b27e20d275edcb92b`

Qualified binary:

- Path: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\b99306303521e97e\codex.exe`
- Version: `codex-cli 0.151.0-alpha.7.2`
- Size: `313790256` bytes
- SHA-256: `bfd4c3b971477a559eadaeae8b1e41382ccb7656bd0104970cf5c6c581f2da7d`
- CLI contract: `98cc8fd6a6ffc1bb0bb4a675d5988cc8f4c31960ada4357003980b5d8befec5b`
- Argv SHA-256: `13760616914d7a1f4579d46e9c6d7eb21965187501bc2bdd820b04d1694923a6`
- Approval/sandbox: `never / read-only`
- Ambient user config: disabled
- Shell/browser/apps/plugins/hooks/multi-agent/image generation: disabled

### Lease And Namespace

- Lease policy: `hermes-live-proof-lease-window/v1`
- Policy ID: `63ab96fe12a3206d7ff7f5281b6c0765c9630e394f7c6b3743bce49409a2bc31`
- TTL: `300` seconds
- Issued: `2026-08-31T14:21:30Z`
- Expires: `2026-08-31T14:26:30Z`
- Process start: `2026-08-31T14:23:26Z` (`184` seconds remained)
- Lease artifact hash: `5ecb36868898b8c07fc9a530881748ad0aaab725577e1efa06c021e1848fb49d`
- Lease manifest SHA-256: `2e9f6e5316961d8d179e3e7ea218762501be0308d5c8fc03b74aef4a159060b4`
- Namespace contract: `hermes-runtime-namespace/v1`
- Namespace: `proof-adb795668b3266a8d95572cc`
- Owner: `ea4d4f-r12e-r6-one-shot`
- Owner hash: `adb795668b3266a8d95572cc0fe59a7fa9de1dd021fa0d0382a6cce54b3c2162`
- Owner manifest SHA-256: `bd2f8af22bc80f459f696880301fdf266b43cde5a85731903e4272d37ee6e956`
- Source binding: `4d8631fae5b17c3c2a84fea65ff63a8e0d579752`
- Historical original/R4 evidence SHA-256 remained
  `67758d5c5843d8f9a0ffb7fc324e3297244c5af7496bbe3b773817091b380f62`
  and `6bc7af15e81f29a4545dc5557608801a4fa87a2ed6733367012f554a0b59eb0a`.

### Fresh R6 Identities

- Delegation: `delegation-7395cae0c86e3c136c262caf11ad8d903ee7de999d6183d962a5c3f62daa1a9e`
- Capability lease: `lease-6813ae6d881de29a8a3ae12adad40780ceb5ecb3006b1b61daec589d5b05df72`
- Mailbox delivery: `mailmsg-f59dfec84e4312c09cef13b411cb747a1883050961a2870f7650d62998b95129`
- Receiver receipt: `receipt-c931ca3547ac95e4e5366b720c60ba69cbde6a442e409ccf11adbc82e6367438`
- Authorization: `execution-authorization-5c2e447f11a95d55`
- Claim: `execution-authorization-claim-6d8d2378893e5f0c`
- Execution attempt: `execution-authorization-attempt-5171ba84ed8dd0ea`
- Route: `a2af26541aebbcececf16947a0f4c8e5d70af9ce4f9f566592ab1e80cbb7c4f5`
- Launch attempt: `latch-a2af26541aebbcececf16947a0f4c8e5d70af9ce4f9f566592ab1e80cbb7c4f5`
- Reservation: `res-a2af26541aebbcececf16947a0f4c8e5d70af9ce4f9f566592ab1e80cbb7c4f5`
- Runtime run: `codex-run-d58e64db01b4a5ea49a0d6f1b3ab5ce2`

### Instance Schema

- Structural policy: `c1c789f1ceb2c56b324bb4b54f26cf10d83380d5bcb9629b20b6f54ec4470dd3`
- Task-input hash: `ac3500f5d26b13af2c01599c1225c91fc7d9ad0d5b917875213adc31e8981f59`
- Receiver-receipt hash: `fdb7e9a32dc87337e474b08c167c39abf41816ca87c229ee4560dc31fecf9d12`
- Schema SHA-256: `ef085667ab50c467419162dc20a925519418b426f55a018378ecd74ad108744d`
- Schema contract SHA-256: `71e33fea5b248cf1accc8671c10e2c8f8126fd0388d37a19ab9b9046be978abb`
- Instance qualification ID: `bf93ba9815154c5991beaefa15ef56a9b88e8892df7e6c1d91f01dc3f7740527`
- Instance lineage hash: `64a3fa1eaf38bf32c385bbbd6d3305db46db8345d8a405e24159e1e180c6ff9d`
- Historical R4 task/receipt lineage was absent from the generated schema.

### Live Stage Results

- Process started: yes, exactly once
- PID: `9432`
- CLI accepted: yes
- Instance schema accepted by live service: yes
- Task accepted: yes
- Model execution reached: yes
- Terminal output received: yes
- Exit code: `0`
- Timed out / cancelled: `no / no`
- Duration: `9.032` seconds
- Structured result parsed: yes
- Instance schema verified: yes
- Independent task/receipt lineage verified: yes
- Evidence manifest verified: yes
- Output scope verified: yes (`output_manifest=[]`)
- Transport terminal state: `VERIFIED`
- Live evidence SHA-256: `03540c7f725ee5e214155efc2e4fcb5c609a9f600ac7bf5ab3d1ba7431c4dce5`
- Stdout SHA-256: `0c37be0213bdb7721eba3b2b84c2f11b5d06f46655e3b90f75c5b38b2bcc2c6a`
- Stderr SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Final-output SHA-256: `93db09ef8f11f1ae46e680732074e3c3a4a5a972dedbc4e6657c2a533f2faefb`

### Earliest Failed Stage

Hermes failed during `PostLaunchExecutionOrchestrator` start-result
reconciliation. `SQLiteExecutionStartStore.persist_execution_start_result()`
attempted to write `runtime_binding_id`, but the prepared `start.sqlite3`
`execution_start_results` table did not contain that column:

`sqlite3.OperationalError: table execution_start_results has no column named runtime_binding_id`

The runtime database reports start schema version `2`. Its launch-attempt table
contains the runtime-binding fields, while its start-result table contains only
the older 18-column shape. This is a real migration/creation-path mismatch in
the live prepared database.

Because the failure occurred before `build_delegation_result()`:

- Canonical result persisted: no
- Result delivery persisted: no
- Originator acknowledgement: no
- COMPLETED projection: no
- Post-result exact/divergent replay: not reached
- Lease extension: no
- Namespace replacement/reuse: no
- Second Codex process: no

The transport row itself is durable as `DEFINITELY_STARTED / VERIFIED`; its
valid output is preserved, but it was not promoted past the required Hermes
result-return boundary.

### Post-Live Regression

| Gate | Result |
| --- | --- |
| R6D | **24 passed, 8 subtests passed** |
| R6C/R6D | **43 passed, 23 subtests passed** |
| R6B | **26 passed, 3 subtests passed** |
| Adapter/CLI | **92 passed** |
| R12A/B/C | **97 passed, 40 subtests passed** |
| Authority/attempt stores | **303 passed** |
| Worker routing | **85 passed** |
| Launch admission/coordinator | **33 passed** |
| Start result | **116 passed** |
| Start-store migration | **11 passed** |
| Authority/start/routing total | **548 passed** |
| Complete Hermes Core | **1,325 passed, 104 subtests passed** |

All post-live CPU/fake gates passed with zero failures. The live mismatch is
therefore preserved as a real-environment schema-initialization defect, not
normalized as an expected failure and not repaired under this live packet.

### Accounting And Boundary

- Original R12E: authorized `1`, started `1`, remaining `0`
- R12E-R4: authorized `1`, started `1`, remaining `0`
- Fresh R12E-R6: authorized `1`, started `1`, remaining `0`
- Second R6 start: `0`
- Retry: none
- Push: no

`CODEX GOVERNED RECEIVER PROCESS/SCHEMA QUALIFICATION: PASS`

`DURABLE AGENT-TO-AGENT RESULT RETURN: FAIL`

`EA-4D.4F CODEX AGENT-TO-AGENT PROOF: FAIL / TERMINAL`

The next boundary is a separately authorized, non-live remediation of the
`execution_start_results` schema creation/migration contract plus a bounded
regression proving fresh databases and migrated databases expose the same
runtime-binding columns. This consumed R6 attempt must never be retried or
rewritten. Any future live proof requires new governance authority and a new
attempt identity.

`DEFINITIVE_STARTS=1`

`REMAINING=0`

`SECOND_LIVE_START=NOT AUTHORIZED`
