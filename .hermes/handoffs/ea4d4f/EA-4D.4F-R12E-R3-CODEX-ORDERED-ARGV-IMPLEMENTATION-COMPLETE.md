# EA-4D.4F-R12E-R3 Ordered Codex CLI Contract Implementation Complete

Date: 2026-08-29

## Disposition

**EA-4D.4F-R12E-R3: PASS / COMMITTED**

The production Codex adapter now requires both the frozen binary identity and
the frozen ordered CLI-contract identity before it can construct an eligible
invocation. No live Codex task or model workload was executed.

## Authority and Repository

- worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- branch: `feature/ea4f-regional-hand-repair-pilot`
- starting HEAD: `a188c735210d9616d8a6c434f3f441909992f3a0`
- frozen R11 SHA-256: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- R12E-R2 design: `PASS / SEMANTIC EQUIVALENT FOUND`
- R12E-R3 commit: the commit containing this completion artifact
- push: no

Strict precheck found no staged or tracked changes. Existing untracked R8-R10,
pytest, and image-pipeline WIP was preserved and remains outside this slice.

## Implementation Surface

Production:

- `tools/hermes_core/codex_adapter.py`

Tests:

- `tests/hermes_core/test_codex_adapter.py`

Documentation:

- `.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R3-CODEX-ORDERED-ARGV-IMPLEMENTATION-COMPLETE.md`
- `.hermes/handoffs/ea4d4f/EA-4D.4F-IMPLEMENTATION-CONTINUATION.md`

No process-controller, result-domain, routing, launch, GPU, ComfyUI, Kilo,
browser, scheduler, Studio Bible/image-pipeline, or Regional Hand Repair file
was changed.

## Ordered Argv Correction

Rejected historical form:

```text
codex.exe exec --ask-for-approval never --sandbox read-only ...
```

Qualified alpha.12.2 form:

```text
codex.exe
  --ask-for-approval never
  --sandbox read-only
  exec
  --json
  --ephemeral
  --ignore-user-config
  --ignore-rules
  --output-schema <trusted-schema-file>
  --output-last-message <adapter-owned-output-file>
  --cd <trusted-working-directory>
  --disable <each frozen capability>
  -
```

The flattened argv must exactly match this adapter-owned order. Approval and
sandbox flags are not duplicated at subcommand level. Missing/reordered flags,
`on-request`, workspace-write, danger-full-access, dangerous bypass,
`--approve-for-me`, or missing user-config isolation all fail qualification
before process capability is reached.

## Binary and CLI Contract Binding

Qualified binary:

- path: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe`
- version: `codex-cli 0.150.0-alpha.12.2`
- SHA-256: `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`

Qualified adapter/contract:

- adapter version: `1.1`
- CLI contract ID: `21f341c1ac959ee3a7c7ce929baf492183bd0d07e7443c0e76e4f22f0196bc02`

The contract ID is SHA-256 of canonical JSON containing:

- adapter version;
- binary version and SHA-256;
- ordered global security options;
- `exec` subcommand identity;
- ordered exec-option template;
- approval, sandbox, ambient-config, structured-output, and stdin policies;
- exact disabled-capability list.

The trusted configuration pins the expected ID. The adapter computes the
actual ID from verified binary material and frozen contract constants. Binary,
version, path, contract, or flattened-argv mismatch fails closed. The contract
ID is included in durable invocation material so replay identity also binds the
qualified contract.

## Security Semantics

```text
APPROVAL_POLICY=NEVER
SANDBOX=READ_ONLY
HUMAN_PROMPTS=NO
AUTO_APPROVE_ARBITRARY_ACTIONS=NO
DANGEROUS_BYPASS=NO
AMBIENT_USER_CONFIG_SECURITY_OVERRIDE=NO
```

`never` means approval-requiring actions are returned as failures rather than
prompting a human. It does not approve arbitrary actions. `--ignore-user-config`
remains an exec-level frozen option, so ambient settings cannot widen the
governed receiver's authority.

## Non-Live Parser Qualification

The qualification method performs only:

1. absolute-path binary hash/version verification;
2. CLI-contract identity verification;
3. exact argv construction/validation;
4. a metadata-only parser call replacing the stdin marker with `--help`.

The real alpha.12.2 parser accepted the complete corrected option set, returned
the `codex exec` usage contract, and did not create or change the task output
artifact.

```text
MODEL_EXECUTION_POSSIBLE=NO
LIVE_CODEX_MODEL_INVOCATIONS=0
NEW_DEFINITIVE_CODEX_STARTS=0
```

## Historical R12E Regression

The original invocation remains immutable:

- invocation: `2878095abb0b500f5dc684eca7c8afe61f2f5e51d70442a7ce1c0c08477e5fe5`
- PID: `660`
- start: `DEFINITELY_STARTED`
- terminal: `FAILED`
- exit code: `2`
- accounting: authorized `1`, definitive starts `1`, remaining `0`

The historical post-`exec` ordering is now a regression fixture and fails
qualification before fake process capability is reached. The terminal replay
invariant remains green. The original runtime/evidence records were not
modified, refrozen, recreated, or relaunched.

## Verification

Interpreter:

`C:\Users\David\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`

All pytest runs used `-q -p no:cacheprovider --tb=short`.

| Gate | Current result |
| --- | --- |
| R12E-R3 / R12D adapter qualification | **90 passed** |
| R12E process controller | **4 passed** |
| R12E result store | **16 passed, 6 subtests passed** |
| R12C | **9 passed** |
| R12B | **38 passed, 25 subtests passed** |
| R12A | **50 passed, 15 subtests passed** |
| Authorization / attempt | **303 passed** |
| Worker routing | **85 passed** |
| Launch admission / coordinator | **33 passed** |
| Start domain/result | **116 passed** |
| Start-store migration | **11 passed** |
| EA-4D.4A | **28 passed** |
| EA-4D.4B | **25 passed** |
| EA-4D.4C | **11 passed** |
| EA-4D.4D | **11 passed** |
| EA-4D.4E | **19 passed** |
| Complete Hermes Core | **1,228 passed, 78 subtests passed** |

## Capability Audit

- changed adapter subprocess calls: two metadata-only `subprocess.run` calls
  for `--version` and parser `--help`;
- live `subprocess.Popen`: unchanged and confined to the separately gated
  R12E process controller;
- generic shell / `shell=True`: no;
- arbitrary executable or PATH fallback: no;
- dangerous bypass / workspace-write expansion: no;
- caller-controlled security policy: no;
- network, browser, MCP, scheduler: no;
- Kilo, GPU, ComfyUI, Studio Bible/image pipeline, RHR: no;
- live task/model start during R12E-R3: zero.

## Governance Boundary

```text
ORIGINAL R12E LIVE PROOF=FAIL / TERMINAL
R12E-R1=HOLD / SUPERSEDED BY R12E-R2 DESIGN
R12E-R2=PASS / SEMANTIC EQUIVALENT FOUND
R12E-R3=PASS / COMMITTED
CURRENT CODEX CLI CONTRACT=QUALIFIED
NEW LIVE PROOF=NOT AUTHORIZED
NEXT GATE=R12E-R4 ONE-SHOT LIVE REQUALIFICATION / NOT AUTHORIZED
PUSH=NO
```
