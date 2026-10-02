# EA-4D.4F-R12E-R6E Codex Successor Binary Requalification

## Disposition

`EA-4D.4F-R12E-R6E: PASS / SUCCESSOR BINARY QUALIFIED`

`EA-4D.4F-R12E-R6D: PASS / READY FOR CLEAN COMMIT`

The replacement Codex executable is qualified for the existing governed,
read-only receiver boundary. Qualification was entirely non-live: no Codex
agent task, model request, real R6 identity, or real R6 runtime state was
created.

## Starting State

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- HEAD: `6646b39946988afe61500ce32a4fe203b8808c19`
- Parent: `e00780bb16ee13f3bad18501b9cc29d96f8b5f16`
- Staged paths: `0`
- R6D tracked modifications: `3`
- R6D new files: `3`
- Unrelated untracked paths: `139`, preserved
- Merge/rebase/cherry-pick: none

R6D remained uncommitted throughout qualification.

## Historical Qualifications

The original qualification remains historical:

- path: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe`
- version: `codex-cli 0.150.0-alpha.12.2`
- SHA-256:
  `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`
- CLI contract:
  `21f341c1ac959ee3a7c7ce929baf492183bd0d07e7443c0e76e4f22f0196bc02`

The R6A successor qualification also remains historical:

- path: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\6ca77c4a9caa4eed\codex.exe`
- version: `codex-cli 0.151.0-alpha.7.1`
- SHA-256:
  `3052f7887c10e97f6cfe4941353bd0763300c4907e49a8688958cb40d4159d89`
- CLI contract:
  `ae576aea601f46634e6ad0d66b9097f78f157d161fdcd2195be6ad6b0db16495`

The R6A executable is no longer present. Its evidence record was not edited or
rebound to replacement bytes.

## Replacement Binary Identity

- exact path:
  `C:\Users\David\AppData\Local\OpenAI\Codex\bin\b99306303521e97e\codex.exe`
- version: `codex-cli 0.151.0-alpha.7.2`
- size: `313790256` bytes
- SHA-256:
  `bfd4c3b971477a559eadaeae8b1e41382ccb7656bd0104970cf5c6c581f2da7d`
- creation time observed UTC: `2026-08-31T13:06:12.4541867Z`
- last-write time observed UTC: `2026-08-30T13:55:31.3573946Z`
- replacement CLI contract ID:
  `98cc8fd6a6ffc1bb0bb4a675d5988cc8f4c31960ada4357003980b5d8befec5b`

Path, size, SHA, and version were recomputed directly before qualification and
again after the complete regression suite. No drift occurred.

## Non-Live CLI Qualification

The existing qualification architecture hashes binary SHA and version into the
CLI contract. The replacement therefore correctly receives a new contract ID.

The qualified surface remains:

- global approval policy `never` before `exec`;
- global sandbox policy `read-only` before `exec`;
- `--json`, `--ephemeral`, `--ignore-user-config`, and `--ignore-rules`;
- trusted result schema, adapter-owned final-output path, and trusted cwd;
- stdin delivery;
- shell, browser, computer, image generation, apps, plugins, hooks, and
  multi-agent capabilities disabled;
- no inherited `PATH`;
- no approve-for-me, dangerous bypass, workspace-write, full access, or extra
  writable directory.

Allowed probes were `--version`, top-level `--help`, `exec --help`, and the
complete ordered parser contract with the stdin marker replaced by `--help`.
The parser returned the `codex exec` usage surface and created no task output
artifact. Model/task execution was not possible in this probe path.

Regression tests retain fail-closed coverage for historical bad global-option
ordering, missing approval policy, unsafe approval policy, missing read-only
sandbox, workspace-write, full access, dangerous bypass, approve-for-me,
missing ambient-config isolation, unknown binary bytes, version drift, and
binary hash drift.

## Original Three Failures

Before R6E these exact nodes failed because the R6A executable path was absent:

1. `BinaryTests::test_historical_binary_identity_is_not_the_successor_qualification`
2. `BinaryTests::test_real_complete_parser_contract_is_accepted_without_model`
3. `BinaryTests::test_real_requalified_binary_is_present_and_exact`

R6E rerun result: **3 passed**.

## Preserved R6D Contract

- policy version: `hermes-live-proof-lease-window/v1`
- policy ID:
  `63ab96fe12a3206d7ff7f5281b6c0765c9630e394f7c6b3743bce49409a2bc31`
- TTL: `300` seconds
- validity: `issued_at <= now < expires_at`
- exact expiry: rejected
- replay/restart extension: no
- renewal/skew/environment override/arbitrary expiry: no

R6C remains `hermes-runtime-namespace/v1`. R6B remains structural policy
`c1c789f1ceb2c56b324bb4b54f26cf10d83380d5bcb9629b20b6f54ec4470dd3`
with instance qualification `codex-instance-schema-qualification/v1`.

## Verification

Interpreter:
`C:\Users\David\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`

| Gate | Result |
| --- | --- |
| Original three failures | **3 passed** |
| Adapter / binary / CLI | **92 passed** |
| R6D | **24 passed, 8 subtests passed** |
| R6C + R6D | **43 passed, 23 subtests passed** |
| R6B | **26 passed, 3 subtests passed** |
| R12A/B/C | **97 passed, 40 subtests passed** |
| Authority/start/routing | **548 passed** |
| Complete Hermes Core | **1,325 passed, 104 subtests passed** |

Zero failures remain. Post-suite binary identity and CLI contract revalidation
passed without drift.

## Capability Audit And Live Accounting

- Live Codex task starts: `0`
- Model executions: `0`
- Real R6 namespace: absent
- Real R6 identities: `0`
- R6 instance schema: none
- R6 live budget consumed: no
- R6 remaining: `1`
- Binary identity weakening: no
- CLI security weakening: no
- Dangerous bypass/workspace-write expansion: no
- Network/browser/MCP/scheduler/Kilo/GPU/ComfyUI/image-pipeline/RHR action: no

## Boundary

`BINARY_IDENTITY_VERIFIED: YES`

`CLI PARSER CONTRACT: PASS`

`CODEX TASK EXECUTION: NO`

`MODEL EXECUTION: NO`

`EA-4D.4F-R12E-R6E: PASS / SUCCESSOR BINARY QUALIFIED`

`NEXT GATE: FRESH R12E-R6 LIVE AUTHORIZATION / NOT AUTHORIZED`

`PUSH: NO`
