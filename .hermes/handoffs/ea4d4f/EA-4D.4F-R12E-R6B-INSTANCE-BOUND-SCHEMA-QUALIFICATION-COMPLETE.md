# EA-4D.4F-R12E-R6B Instance-Bound Schema Qualification Complete

## Disposition

`EA-4D.4F-R12E-R6B: PASS / READY FOR CLEAN COMMIT`

R6B separates the reusable result-schema structure from the lineage constants
that belong to one governed delegation. It is entirely non-live: no real R6
identity, runtime state, Codex process, or model invocation was created.

## Precheck

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- Starting HEAD: `be8e1101b233a087b3f2192bf54d7d2867468055`
- Parent: `6dd547caeb54df65fa62c3509e553773985aaf1a`
- Frozen R11 SHA-256: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- Tracked modifications before R6B: `0`
- Staged files before R6B: `0`
- New R6-specific runtime items before and after R6B: `0`
- Shared historical `r12e` runtime folder: `9` retained items; no item was
  created, rewritten, or removed by R6B
- Unrelated untracked R8-R10, pytest, and image-pipeline WIP: preserved

## Root Cause

Historical R5 qualification remains immutable:

- Canonical schema hash:
  `b2d9872bb704cbe4a65619b70f938a13e1b4941ba82e4256eec717a4733902fe`
- Historical schema qualification ID:
  `7b404540518df2b9373c99eb614f2e610d159548c6aceca394260be9c21565e9`
- Embedded R4 task-input hash:
  `d0116ebcb0bdfe89960a12345871c54d064bb81e76a56112d8ee32f02fd7463c`
- Embedded R4 receiver-receipt hash:
  `d03816c318b4d39b79be8ae9b1babcf148367013e03c7aeff5eb7e6a49191f86`

The old qualifier treated complete schema content as one reusable contract.
Because the content contains task and receipt constants, reusing it across
delegations would bind a fresh R6 result to R4 lineage. The R6 HOLD correctly
rejected that before durable identity creation or process capability.

## Structural Policy

- Policy version: `codex-result-structural-policy/v1`
- Structural policy ID:
  `c1c789f1ceb2c56b324bb4b54f26cf10d83380d5bcb9629b20b6f54ec4470dd3`
- Result schema ID: `hermes.delegation_result/v1`
- Validator policy: `codex-structured-output-schema/v1`

The structural identity includes the complete R5 topology and strictness:
seven explicitly typed constants, all required fields, closed objects,
empty-only closed `output_manifest.items`, exact evidence cardinality/type,
null success error fields, canonical serialization, and the exact locations,
types, formats, and durable sources of instance parameters.

Only two instance parameters are allowed:

| Parameter | Canonical source | Schema path |
| --- | --- | --- |
| `task_input_hash` | `canonical_delegated_task.task_input_hash` | `$.properties.result_payload.properties.task_input_hash.const` |
| `receiver_receipt_hash` | `durable_delegation_receipt.artifact_hash` | `$.properties.evidence_manifest.items.properties.sha256.const` |

Both are required canonical lowercase 64-character SHA-256 values. Unknown,
missing, malformed, uppercase, dictionary-based, or conflicting substitutions
are rejected. No free-form caller override path exists.

## Instance Qualification

Qualification version: `codex-instance-schema-qualification/v1`.

An instance qualification binds:

- structural policy ID;
- canonical instance schema hash;
- task/receipt lineage hash;
- successor binary SHA-256 and version;
- CLI contract ID;
- validator policy/version.

Fake instance A:

- Task hash: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Receipt hash: `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`
- Lineage hash: `1669e1ccb2c61147c25e1698a424ed38421b5b817b45c1d8892b143ed8873f51`
- Schema hash: `88f3614c589ddf8e2e263fd758e02b1b41b57ec5da92b2e80441b66249867476`
- Qualification ID: `24f09a24b4f34cd76f41eed1560697b868ae46163eb8d0b076d84689b44ead16`

Fake instance B:

- Task hash: `cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc`
- Receipt hash: `dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd`
- Lineage hash: `64b26e083fa10c877970bb1915265152d24cf6224e9d6fbe2fde97db5d6e58c7`
- Schema hash: `4296ae27fa325375a6a32af49c995ee9a6fb75bcc594cc85542be4cdcb0bc85c`
- Qualification ID: `c503f3e8295427c7bc78f695161dff114dca8bf92d55195506ab47796fdce1ed`

Both instances have the same structural policy ID. Their lineage hashes,
schema hashes, and qualification IDs are distinct. Repeating either fixture
produces byte-identical schema and qualification records, including after the
schema is reopened from disk.

The historical R5 schema qualifies only against its own R4 task/receipt
lineage. Qualifying it for fake instance B fails with `instance schema does not
match durable lineage and structural policy`. Binary, CLI, policy, schema,
qualification-ID, or lineage drift also fails closed.

## Eligibility Ordering

The committed R12E preparation now follows:

`durable task + receipt -> instance schema -> generic structural audit ->`
`instance lineage/environment qualification -> PREPARED transport record`

The preflight freezes the structural policy ID, instance schema hash, instance
lineage hash, and instance qualification ID. Execute/replay reconstructs the
expected qualification from the persisted task and receipt and compares all
four values before process capability.

Tests prove no process capability when identity binding is incomplete, schema
is absent, qualification enforcement is disabled, schema belongs to another
instance, or qualification identity drifts. A fully qualified fake instance
can become `PREPARED` but starts no process.

## Verification

Interpreter:
`C:\Users\David\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`

| Gate | Result |
| --- | --- |
| R6B instance-schema qualification | **26 passed, 3 subtests passed** |
| Adapter | **92 passed** |
| R5 schema regression | **26 passed** |
| Process controller | **4 passed** |
| Result store | **16 passed, 6 subtests passed** |
| R12C | **9 passed** |
| R12B | **38 passed, 25 subtests passed** |
| R12A | **50 passed, 15 subtests passed** |
| Authority/start/routing subset | **575 passed, 20 subtests passed** |
| Complete Hermes Core | **1,282 passed, 81 subtests passed** |

`py_compile` and `git diff --check` passed. Zero focused or broad failures
remain.

## Capability Audit

- Live Codex processes/model invocations: `0 / 0`
- Real R6 identities/runtime state: `0 / none`
- R6 live budget consumed: no
- Generic shell/arbitrary executable: no
- Dangerous bypass/workspace-write expansion: no
- Network, browser, MCP, scheduler, Kilo, GPU, ComfyUI, Studio Bible/image
  pipeline, or Regional Hand Repair action: no
- Original R12E evidence SHA-256:
  `67758d5c5843d8f9a0ffb7fc324e3297244c5af7496bbe3b773817091b380f62`
- R12E-R4 evidence SHA-256:
  `6bc7af15e81f29a4545dc5557608801a4fa87a2ed6733367012f554a0b59eb0a`

## Accounting And Boundary

- Original R12E: authorized `1`, started `1`, remaining `0`
- R12E-R4: authorized `1`, started `1`, remaining `0`
- Current R12E-R6: authorized `1`, started `0`, remaining `1`
- R12E-R6B live starts/real identities: `0 / 0`

`STRUCTURAL RESULT SCHEMA POLICY: QUALIFIED`

`INSTANCE-BOUND SCHEMA DERIVATION: QUALIFIED`

`CROSS-DELEGATION SCHEMA REUSE: FAIL-CLOSED`

`LIVE CODEX START: NOT AUTHORIZED`

The next gate is a fresh R12E-R6 live authorization bound to the committed R6B
HEAD, structural policy ID, successor binary/CLI identities, and instance
qualification version. R6B itself does not authorize that start.
