# EA-4D.4F-R12E-R6A Codex Binary Requalification

## Disposition

`EA-4D.4F-R12E-R6A: PASS / READY FOR CLEAN COMMIT`

The installed Codex successor is qualified for the existing governed,
read-only receiver boundary without starting a Codex task or creating any
R12E-R6 governed identity. R12E-R6 remains `HOLD / NOT STARTED`; its one-start
budget remains unused and cannot be exercised under the R6A packet.

## Precheck

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- Starting HEAD: `6dd547caeb54df65fa62c3509e553773985aaf1a`
- Parent: `ee0ba803c94dd78d01d0e45715c7459bcc8b3a8f`
- Frozen R11 SHA-256: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- Tracked modifications before R6A: `0`
- Staged files before R6A: `0`
- Unrelated untracked R8-R10, pytest, and image-pipeline WIP: preserved

## Binary Identity

Historical qualification remains explicit and unchanged:

- Path: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe`
- Version: `codex-cli 0.150.0-alpha.12.2`
- SHA-256: `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`
- CLI contract ID: `21f341c1ac959ee3a7c7ce929baf492183bd0d07e7443c0e76e4f22f0196bc02`

Successor qualification:

- Canonical path: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\6ca77c4a9caa4eed\codex.exe`
- Version: `codex-cli 0.151.0-alpha.7.1`
- SHA-256: `3052f7887c10e97f6cfe4941353bd0763300c4907e49a8688958cb40d4159d89`
- Size: `313923888` bytes
- Creation time UTC observed: `2026-08-30T13:54:44Z`
- Last-write time UTC observed: `2026-08-29T13:31:05Z`

The old and successor identities are distinct. A configuration that presents
the historical SHA/version as the successor fails before the version probe or
process capability.

## CLI Contract

The successor parser accepted the complete qualified ordering:

`codex.exe --ask-for-approval never --sandbox read-only exec ...`

The exact frozen execution surface retains:

- approval policy `never`;
- sandbox policy `read-only`;
- `--ignore-user-config` and `--ignore-rules` after `exec`;
- JSONL output, trusted `--output-schema`, adapter-owned
  `--output-last-message`, trusted `--cd`, and stdin input;
- explicit disabling of shell, browser, computer, image generation, apps,
  plugins, hooks, and multi-agent capabilities;
- no `--approve-for-me`, dangerous bypass, workspace-write, full access,
  extra writable directory, or inherited `PATH`.

`--version`, top-level `--help`, `exec --help`, and the complete ordered
parser-only invocation were inspected. The parser-only invocation replaced the
stdin prompt marker with `--help`, returned the `codex exec` usage surface, and
did not create a task output artifact.

Because CLI contract material includes binary SHA-256 and version, the
successor receives a new deterministic CLI contract ID:

- Old: `21f341c1ac959ee3a7c7ce929baf492183bd0d07e7443c0e76e4f22f0196bc02`
- New: `ae576aea601f46634e6ad0d66b9097f78f157d161fdcd2195be6ad6b0db16495`

## Result Schema Contract

The R12E-R5 schema bytes and local policy remain unchanged:

- Result schema ID: `hermes.delegation_result/v1`
- Qualification policy: `codex-structured-output-schema/v1`
- Canonical schema hash: `b2d9872bb704cbe4a65619b70f938a13e1b4941ba82e4256eec717a4733902fe`
- Schema qualification ID: `7b404540518df2b9373c99eb614f2e610d159548c6aceca394260be9c21565e9`

The schema qualification ID is intentionally content/policy scoped. It does
not change merely because the executable changed. Live eligibility composes
three independent exact gates: successor binary identity, successor CLI
contract ID, and the unchanged schema hash/qualification ID. Tests reject a
qualified schema paired with an unknown CLI environment before process
capability.

The corrected seven explicitly typed constants and closed empty-only
`output_manifest.items` remain locally qualified. The historical R12E-R4 bad
schema remains rejected. The CLI still exposes no safe schema-only service
validator, so live service acceptance is not claimed by R6A.

## Verification

Interpreter:

`C:\Users\David\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`

| Gate | Result |
| --- | --- |
| Adapter successor qualification | **92 passed** |
| R12E-R5 schema qualification | **26 passed** |
| Process controller | **4 passed** |
| Result store | **16 passed, 6 subtests passed** |
| R12C | **9 passed** |
| R12B | **38 passed, 25 subtests passed** |
| R12A | **50 passed, 15 subtests passed** |
| Authority/start/routing subset | **575 passed, 20 subtests passed** |
| Complete Hermes Core | **1,256 passed, 78 subtests passed** |

`py_compile` and `git diff --check` passed. Zero focused or broad failures
remain.

## Capability Audit

- Codex task/model process starts: `0`
- Model invocations: `0`
- R12E-R6 identities created: `0`
- R12E-R6 runtime/evidence path: absent
- Generic shell or arbitrary executable capability: no
- Dangerous bypass or workspace-write expansion: no
- Ambient policy widening: no
- Network, browser, MCP, scheduler, Kilo, GPU, ComfyUI, Studio Bible/image
  pipeline, or Regional Hand Repair action: no
- Original R12E evidence SHA-256:
  `67758d5c5843d8f9a0ffb7fc324e3297244c5af7496bbe3b773817091b380f62`
- R12E-R4 evidence SHA-256:
  `6bc7af15e81f29a4545dc5557608801a4fa87a2ed6733367012f554a0b59eb0a`

## Live Accounting

- Original R12E: authorized `1`, started `1`, remaining `0`
- R12E-R4: authorized `1`, started `1`, remaining `0`
- R12E-R6: authorized `1`, started `0`, remaining `1`
- R12E-R6A live starts: `0`

## Governance Boundary

`CODEX SUCCESSOR BINARY: QUALIFIED`

`CLI CONTRACT: QUALIFIED`

`RESULT SCHEMA CONTRACT: QUALIFIED FOR SUCCESSOR`

`R12E-R6: HOLD / NOT STARTED PRESERVED`

`R12E-R6 LIVE BUDGET: 1 REMAINING`

`NEXT GATE: FRESH R12E-R6 LIVE AUTHORIZATION / NOT AUTHORIZED`

No live Codex start, production activation, scheduler activation, or push is
authorized by this record.
