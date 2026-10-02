# EA-4D.4F-R12E-R2 Codex Approval/Sandbox Redesign

Date: 2026-08-29

## Decision

**R12E-R2 DESIGN: PASS / SEMANTIC EQUIVALENT FOUND**

The current Codex binary still supports the frozen R11 security semantics. The
R12E failure was caused by version-specific option placement, not removal of
the approval policy. In alpha.12.2, `--ask-for-approval never` is a top-level
option and must appear before `exec`. The failed R12E argv placed it after
`exec`, where the subcommand parser rejected it.

This gate does not authorize production changes or a new live proof.

## Repository Record

- worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- branch: `feature/ea4f-regional-hand-repair-pilot`
- required starting HEAD: `d7f7a0036997a2777b69c471816a4b7704e47219`
- terminal-failure/HOLD evidence commit: `9d14202`
- frozen R11 SHA-256: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- unrelated untracked R8-R10, pytest, and image-pipeline WIP: untouched
- push: no

## Frozen R11 Semantics

R11 requires a local, unattended, least-authority Codex receiver:

- no interactive human approval path;
- approval-requiring operations fail closed rather than being auto-approved;
- read-only filesystem policy;
- canonical task input on stdin;
- explicit trusted working directory, schema, environment, and output path;
- no shell-built command string;
- execution, browser, image, app, plugin, hook, or multi-agent capabilities
  disabled;
- durable idempotency and no duplicate process after uncertain or definitive
  start.

The security property is "never prompt a human and never widen authority," not
"automatically approve every operation." Codex describes the `never` policy as
never asking for approval and returning execution failures to the model. That
is the required fail-closed behavior.

## Version-Specific Mechanisms

### alpha.8 mechanism frozen by R11

```text
codex.exe exec ... --ask-for-approval never --sandbox read-only ...
```

Binary:

- version: `codex-cli 0.150.0-alpha.8`
- SHA-256: `09d6723925e724edf0bbbbc7b9e204526e0fb1462c86bd2a4997311fd5071eba`

### alpha.12.2 failed R12E mechanism

The same post-subcommand placement failed before task acceptance:

- invocation: `2878095abb0b500f5dc684eca7c8afe61f2f5e51d70442a7ce1c0c08477e5fe5`
- PID: `660`
- start classification: `DEFINITELY_STARTED`
- exit code: `2`
- terminal state: `FAILED`
- stderr: `error: unexpected argument '--ask-for-approval' found`
- model/task execution: not reached
- one-shot authority: consumed permanently

This evidence is immutable and the invocation is never reusable.

### alpha.12.2 supported mechanism

Current binary:

- path: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe`
- version: `codex-cli 0.150.0-alpha.12.2`
- SHA-256: `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`

`codex --help` exposes both top-level options:

```text
-a, --ask-for-approval <APPROVAL_POLICY>  on-request | never
-s, --sandbox <SANDBOX_MODE>              read-only | workspace-write | danger-full-access
```

`codex exec --help` exposes `--sandbox` but not `--ask-for-approval`. The
supported successor therefore places both security options before `exec`:

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

The complete option set was submitted to the alpha.12.2 parser with `--help`
instead of a prompt. It exited `0`, created no output file, and made no model
call. This proves option placement and mutual compatibility. It does not prove
live task acceptance; that remains a separately authorized future proof.

## Configuration Inspection

The binary contains recognized `approval_policy` and `sandbox_mode` config
fields. A non-live `doctor --json` inspection with:

```text
-c approval_policy="never" -c sandbox_mode="read-only"
```

reported approval policy `Never` and restricted filesystem/network policy.
The same diagnostic with `--ask-for-approval never --sandbox read-only`
reported the same effective policy. No model task was invoked.

The successor does not depend on ambient config or config-key overrides. It
uses trusted top-level flags plus `exec --ignore-user-config`. The delegated
task cannot choose security flags, config, executable, working directory, or
environment. The local user setting `windows.sandbox = "elevated"` is therefore
not part of governed execution.

`--strict-config` combined with `--help` did not validate an intentionally
unknown `-c` override, because help short-circuits config loading. A future
qualification test must use a temporary config home and a metadata-only command
that fully loads config, and must explicitly prove an invalid key fails. The
runtime contract does not use such an override.

## Preparation Versus Execution State

The ignored `preflight.json` is an immutable preparation snapshot. It correctly
records the state at preparation time (`remaining=1`, `definitive_starts=0`). It
is not the current execution state.

Current execution truth is held separately:

- the transport registry row is `DEFINITELY_STARTED / FAILED`, PID `660`;
- `live-proof-evidence.json` records one definitive start and zero remaining;
- the harness refuses execution whenever that evidence file exists;
- adapter replay returns any terminal registry record without calling a process
  capability;
- preflight refreeze requires `PREPARED`, no terminal state, and no PID, so the
  failed row is ineligible.

A focused non-live regression now covers `DEFINITELY_STARTED / FAILED` replay
and proves a second call does not spawn another fake process.

Required invariant: `FAILED LIVE INVOCATION REUSABLE=NO`.

## Mode Matrix

| Mechanism | Approval behavior | Sandbox behavior | Decision |
| --- | --- | --- | --- |
| `--sandbox read-only` alone | Defaults to `on-request`; interactive path remains | Read-only/restricted | Rejected for unattended receiver |
| top-level `--ask-for-approval never --sandbox read-only` | No human prompt; failed actions return to model | Read-only/restricted | Selected |
| `--approve-for-me` | Automatic review | Forces workspace-write; parser rejects coexistence with explicit read-only | Rejected: authority expansion |
| `--dangerously-bypass-approvals-and-sandbox` | No prompts | No sandbox | Prohibited |
| config `approval_policy=never`, `sandbox_mode=read-only` | Equivalent fields are recognized | Read-only/restricted | Valid evidence, not selected runtime mechanism |
| post-`exec --ask-for-approval never` | Rejected by alpha.12.2 subcommand parser | No task starts | Rejected old placement |

## Security Invariant Matrix

| Invariant | Successor preservation |
| --- | --- |
| Hermes retains authority | Adapter-owned immutable argv and lease lineage |
| Receiver gets no broader lease | Read-only plus disabled capability set |
| No interactive approval | Top-level approval policy `never` |
| No uncontrolled human prompt | Noninteractive `exec`; approval failure returns to model |
| No unsandboxed execution | Explicit `read-only`; dangerous bypass prohibited |
| No arbitrary file write | Read-only policy; only adapter-owned process capture occurs outside receiver tools |
| No arbitrary executable/shell | Pinned executable, structured argv, `shell=False`, shell tool disabled |
| No caller-controlled security policy | Security tokens are trusted adapter constants, not envelope fields |
| No ambient config override | `--ignore-user-config` plus explicit trusted security flags |
| No retry after uncertain/definite start | Durable terminal/start replay gate and immutable evidence |

## Rejected Alternatives

- Dangerous bypass removes the required sandbox.
- `--approve-for-me` introduces workspace-write and cannot coexist with explicit
  `--sandbox read-only`.
- Read-only alone retains an interactive approval path.
- Treating approval requests as a new Hermes protocol is unnecessary because
  the supported `never + read-only` combination exists.
- Switching receivers is unnecessary for this compatibility defect.

## R12D Qualification Correction

R12D proved individual help surfaces but did not prove the final argv was
accepted. Future qualification must bind two identities:

```text
BINARY IDENTITY + CLI CONTRACT ID
```

Binary identity includes absolute path, version, full SHA-256, and size. CLI
contract identity must hash a canonical preimage containing:

- ordered complete argv tokens and option placement;
- adapter version;
- trusted environment-name allowlist;
- working-directory/schema/output-path policy;
- disabled capability set;
- approval and sandbox semantics;
- parser qualification result.

Any binary hash/version or CLI-contract change fails closed pending
requalification. Qualification must validate the complete intended argv with a
non-live parser command, prove no output/model call occurs, and reject the
deprecated placement. Parser-only validation cannot establish model/task
acceptance; a separately authorized one-shot proof is still required.

## Authorized Next Implementation Surface

This design packet does not authorize implementation. A successor
implementation packet should be limited to:

1. Reorder trusted adapter argv so approval/sandbox precede `exec`.
2. Add a canonical CLI-contract identity and fail-closed verification.
3. Add metadata-only parser/config qualification helpers and tests.
4. Preserve all existing binary, environment, path, capability, process,
   timeout, result, and replay controls.
5. Update R12E harnesses to require a new invocation identity and authority;
   never alter or reuse the original terminal invocation.

No EA-4D.4A-E semantics, agent routing, Studio Bible/image pipeline, GPU,
ComfyUI, browser, scheduler, or Regional Hand Repair implementation is in scope.

## Design Test Plan

The next implementation gate must test, without a model call:

- exact path/version/full SHA-256 and binary-update failure;
- exact ordered argv and CLI-contract hash;
- top-level approval flag placement accepted;
- deprecated post-`exec` placement rejected;
- approval policy `Never` and sandbox `read-only` interpreted independently;
- ambient user config ignored;
- valid config fields interpreted and invalid config file/key rejected;
- `--approve-for-me` plus read-only rejected;
- dangerous bypass absent;
- all disabled capabilities present exactly once;
- task/envelope cannot alter security policy;
- terminal/unknown invocation replay creates no process;
- process-start and task-accepted remain distinct;
- qualification produces no task/thread/output artifact and no model call;
- binary or CLI-contract drift fails closed.

## Future Live-Proof Requirements

No future live proof is authorized by R12E-R2. A later packet must authorize a
new one-shot proof with:

- new delegation, launch, runtime, invocation, and authorization identities;
- new explicit live budget;
- committed corrected source;
- newly frozen binary identity and CLI-contract identity;
- fresh preflight and evidence paths;
- the original failed invocation retained terminal forever.

## Remaining Risks

- Parser-only success cannot prove end-to-end task acceptance.
- The diagnostic reports effective policy but does not replace a future live
  proof of the full no-tool model-visible contract.
- Alpha CLI behavior may change on any binary update; both identities must be
  requalified.
- Strict unknown-key behavior needs a dedicated temporary-config qualification
  because `--help` short-circuits config loading.
- The current production adapter still contains the rejected post-`exec`
  placement until a separate implementation packet authorizes correction.

## Governance Disposition

```text
ORIGINAL R12E: FAIL / TERMINAL / IMMUTABLE
R12E-R1: SUPERSEDED ONLY AS TO "NO EQUIVALENT" FINDING
R12E-R2 DESIGN: PASS / SEMANTIC EQUIVALENT FOUND
PRODUCTION REDESIGN IMPLEMENTATION: NOT AUTHORIZED
NEW LIVE CODEX START: NOT AUTHORIZED
LIVE MODEL INVOCATION: NOT AUTHORIZED
ORIGINAL LIVE BUDGET: AUTHORIZED=1 / DEFINITIVE_STARTS=1 / REMAINING=0
R12E-R2 LIVE_STARTS=0
PUSH=NO
```
