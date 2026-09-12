# EA-4D.4F-R12E-R5 Schema-Contract Remediation Complete

## Disposition

`EA-4D.4F-R12E-R5: PASS / NOT YET COMMITTED`

R12E-R5 repairs and qualifies the trusted Codex structured-output schema
entirely without a live Codex task. New and still-`PREPARED` invocations now
fail closed unless their exact canonical schema hash passes the constrained
structured-output qualification policy. Already-terminal historical records
remain replay-readable without being requalified or relaunched.

## Precheck

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- Starting HEAD: `ee0ba803c94dd78d01d0e45715c7459bcc8b3a8f`
- Parent: `aa43385d073480add4d6e5ac1fccea1cbb195e6d`
- Frozen R11 SHA-256: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- Staged files before work: `0`
- Tracked modifications before work: `0`
- Merge/rebase/cherry-pick state: none
- Unrelated untracked R8-R10, pytest, and image-pipeline WIP: preserved

## R12E-R4 Failure Preservation

- Invocation ID: `8e2ead9147f4afb985113f710f2f107b0450b809480651bd484f411c745706b1`
- PID: `7196`
- Start classification: `DEFINITELY_STARTED`
- Terminal state: `FAILED`
- Exit code: `1`
- Failure boundary: `STRUCTURED OUTPUT SCHEMA VALIDATION / PRE-MODEL`
- Failed schema file SHA-256: `51548a8306b76e273a83f0dfc22c687aae8ede6722d5aa0a4998234983634887`
- R12E-R4 evidence SHA-256: `6bc7af15e81f29a4545dc5557608801a4fa87a2ed6733367012f554a0b59eb0a`
- Accounting: authorized `1`, started `1`, remaining `0`

The original R12E evidence SHA-256 remains
`67758d5c5843d8f9a0ffb7fc324e3297244c5af7496bbe3b773817091b380f62`.
Neither terminal experiment was reset, refrozen, or relaunched.

## Root Cause

The exact failed schema was recovered from:

`.hermes/runtime/ea4d4f/r12e-r4/hermes-result-v1.schema.json`

The first service-reported failure path was:

`$.properties.evidence_manifest.items.properties.evidence_type`

Failed fragment:

```json
{"const":"receiver_acceptance_sha256"}
```

The qualified structured-output contract requires an explicit type matching
the constant:

```json
{"type":"string","const":"receiver_acceptance_sha256"}
```

The full audit found the same missing-type defect on seven constants:

- `schema_version`: string
- `outcome`: string
- `result_payload.qualification_statement`: string
- `result_payload.task_input_hash`: string
- `evidence_manifest.items.ordinal`: integer
- `evidence_manifest.items.evidence_type`: string
- `evidence_manifest.items.sha256`: string

It also found that `output_manifest` lacked an explicit `items` schema. It
remains constrained to `maxItems: 0`; adding a closed empty object item schema
does not widen the accepted result set.

## Semantic Equivalence

The result contract remains `hermes.delegation_result/v1`; this is a validator
representation correction, not a semantic schema-version change.

The corrected schema still requires:

- the same seven top-level fields;
- `additionalProperties: false` for every object;
- the same exact success outcome, statement, task hash, evidence ordinal/type/hash;
- an empty output manifest;
- exactly one evidence item;
- null error fields.

Focused instance validation proves the intended frozen result is accepted and
wrong constants, wrong types, missing fields, extra fields, malformed evidence,
and nonempty output scope are rejected.

## Schema Qualification

- Qualification policy: `codex-structured-output-schema/v1`
- Failed R12E-R4 canonical schema hash: `94d50718b5d25c1a950a589070ef3ccf9dacad71c7cc8de14381275469d03884`
- Qualified R12E-R5 canonical schema hash: `b2d9872bb704cbe4a65619b70f938a13e1b4941ba82e4256eec717a4733902fe`
- Qualified R12E-R5 file SHA-256: `3d3eff95822e4f3aba8e33e82c67fcfe518ea43b12a15760373489152e769a93`
- Schema qualification ID: `7b404540518df2b9373c99eb614f2e610d159548c6aceca394260be9c21565e9`
- Schema compatibility audit: `PASS`
- Binary SHA-256: `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`
- CLI contract ID: `21f341c1ac959ee3a7c7ce929baf492183bd0d07e7443c0e76e4f22f0196bc02`

The local qualifier canonicalizes the complete schema and recursively enforces:

- one explicit supported type per node;
- type-compatible constants and enums;
- closed objects with every property required;
- explicit array item schemas and valid bounds;
- rejection of unsupported composition/keywords;
- deterministic schema and qualification identities.

Future preparation is eligible only when binary, CLI contract, and exact schema
contract all pass. Missing qualification, hash mismatch, schema drift, and the
historical R12E-R4 schema fail before process capability.

The qualified Codex CLI exposes no safe schema-only service validation command.
`codex exec --help` validates the complete argv parser path but does not submit
the schema to the model service. Therefore:

- deterministic local schema qualification: `PASS`;
- parser-only argv validation: `PASS`;
- parser output artifact changed: `NO`;
- model execution possible during validation: `NO`;
- live-service schema acceptance: `NOT CLAIMED / OWNED BY A FUTURE AUTHORIZED LIVE GATE`.

## Implementation

Changed production/test surfaces:

- `tools/hermes_core/codex_adapter.py`
- `tests/hermes_core/run_r12e_live_proof.py`
- `tests/hermes_core/test_codex_adapter.py`
- `tests/hermes_core/test_codex_schema_contract.py`

The adapter now qualifies schema material before any new or `PREPARED`
invocation is reserved/executed. The harness writes explicit constant types,
records canonical schema and qualification identities in preflight, and checks
both before execution. Terminal replay remains non-executing and available even
when historical schema material is no longer qualified.

No result-store, delivery, acknowledgement, completion projection, authority,
routing, launch, start, scheduler, or image-pipeline code changed.

## Verification

Interpreter:

`C:\Users\David\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`

All pytest runs used isolated repository-local temporary roots, `-q`,
`-p no:cacheprovider`, and `--tb=short`.

| Gate | Result |
| --- | --- |
| R12E-R5 schema qualification | **25 passed** |
| Codex adapter | **90 passed** |
| Process controller | **4 passed** |
| Result store | **16 passed, 6 subtests passed** |
| R12C | **9 passed** |
| R12B | **38 passed, 25 subtests passed** |
| R12A | **50 passed, 15 subtests passed** |
| Complete Hermes Core | **1,253 passed, 78 subtests passed** |

`py_compile` and `git diff --check` passed. Zero focused or broad failures
remain.

## Capability Audit

- Live Codex process starts: `0`
- Model invocations: `0`
- New live budget: none
- R12E-R5 transport database: none
- R12E-R5 spool/output artifacts: none
- Generic shell / arbitrary executable: no
- Dangerous bypass / workspace-write expansion: no
- Ambient config security control: no
- Network, browser, MCP, scheduler: no
- Kilo, GPU, ComfyUI, Studio Bible/image pipeline, RHR: no

Only the already-qualified executable's `--version` metadata probe and
`exec --help` parser probe ran. Neither can execute a model task.

## Governance Boundary

```text
R12E ORIGINAL=FAIL / TERMINAL / IMMUTABLE
R12E-R1=HOLD
R12E-R2=PASS
R12E-R3=PASS / COMMITTED
R12E-R4=FAIL / TERMINAL / IMMUTABLE
R12E-R5=PASS / NOT YET COMMITTED
CODEX BINARY IDENTITY=QUALIFIED
CODEX CLI CONTRACT=QUALIFIED
CODEX RESULT SCHEMA CONTRACT=QUALIFIED LOCALLY
NEW LIVE START=NOT AUTHORIZED
R12E-R6=NOT AUTHORIZED
PUSH=NO
```
