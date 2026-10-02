# EA-4D.4F Codex Binary Requalification

Date: 2026-08-29

## Decision

`CODEX BINARY REQUALIFICATION: PASS / RE-FROZEN`

This successor qualification supersedes only the executable identity used for
future R12D/R12E Codex adapter work. It does not rewrite or amend the frozen R11
architecture.

## Historical identity

- Version: `codex-cli 0.150.0-alpha.8`
- SHA-256: `09d6723925e724edf0bbbbc7b9e204526e0fb1462c86bd2a4997311fd5071eba`
- Reviewed path:
  `C:\Users\David\AppData\Local\OpenAI\Codex\bin\d0097be4feba73d0\codex.exe`
- Replacement reason: the reviewed path and exact binary are no longer present
  after the local Codex application update.

## Successor identity

- Canonical path:
  `C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe`
- Version: `codex-cli 0.150.0-alpha.12.2`
- SHA-256: `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`
- File size: `310753072` bytes
- Availability: present and callable

Future adapter invocation must bind this exact canonical path, version, and
complete SHA-256. Bare `codex.exe` or PATH lookup is not qualified.

## Non-live probes

All probes used the exact successor path and were metadata/help inspections.
No `codex exec`, prompt submission, agent task, or model workload occurred.

| Probe | Purpose | Exit |
|---|---|---:|
| `codex.exe --version` | Exact CLI family and version | 0 |
| `codex.exe --help` | Root command and global-option surface | 0 |
| `codex.exe exec --help` | Unattended argv, stdin, JSONL, schema, output, cwd, sandbox, and config surface | 0 |
| `codex.exe debug --help` | Availability of non-model debug inspection | 0 |
| `codex.exe debug prompt-input --help` | Model-visible input inspection contract | 0 |
| `codex.exe debug prompt-input` with the frozen disabled-feature set | Validate accepted disables and inspect model-visible input JSON | 0 |

The final probe returned valid JSON containing only model-visible message
objects. It contained no prohibited tool declaration. The text
`multi_agent` occurred only inside a developer policy message that disables
proactive delegation; it was not a tool declaration or capability exposure.

## Compatibility matrix

| R12D dependency | Observed successor behavior | Classification | Result |
|---|---|---|---|
| Binary resolution | Exact absolute file exists and is callable | Compatible change | PASS |
| Version format | Reports `codex-cli <semantic prerelease>` | Unchanged | PASS |
| Command/subcommand | `exec` remains the noninteractive command | Unchanged | PASS |
| Structured output | `--json` remains documented JSONL output | Unchanged | PASS |
| Final schema | `--output-schema <FILE>` remains supported | Unchanged | PASS |
| Final output spool | `--output-last-message <FILE>` remains supported | Unchanged | PASS |
| Noninteractive behavior | `exec`, `--ephemeral`, approval `never`, and read-only sandbox remain supported | Unchanged | PASS |
| Input delivery | `-` still reads instructions from stdin | Unchanged | PASS |
| Working directory | `--cd <DIR>` remains supported | Unchanged | PASS |
| User-config isolation | `--ignore-user-config` remains supported; authentication may still use `CODEX_HOME` | Unchanged | PASS |
| Rules isolation | `--ignore-rules` remains supported | Unchanged | PASS |
| Feature disabling | Every frozen `--disable <FEATURE>` value is accepted by prompt-input inspection | Unchanged | PASS |
| Model-visible inspection | `debug prompt-input` returns valid JSON without model execution | Unchanged | PASS |
| Timeout integration | No CLI timeout is required; adapter-owned process timeout remains representable | Unchanged | PASS |
| Cancellation integration | A normal local process boundary remains available for adapter-owned bounded termination | Unchanged | PASS |
| Exit/result contract | Exit status, JSONL stdout, separate stderr, schema, and final-output file remain representable | Unchanged | PASS |
| Windows argv | All required values remain separate argv elements; no shell string is required | Unchanged | PASS |

Runtime event ordering, terminal-result validation, timeout/cancellation state,
and replay behavior remain R12D fake-process qualification concerns. One live
end-to-end result remains the separately bounded R12E proof; this
requalification did not attempt to prove those behaviors with a model call.

## Accounting

- `MODEL_AGENT_EXECUTION_POSSIBLE=NO` for every probe used here.
- `CODEX_AGENT_TASK_STARTED=NO`
- `R12E_AUTHORIZED_LIVE_INVOCATIONS=1`
- `R12E_DEFINITIVE_STARTS=0`
- `R12E_REMAINING=1`
- GPU / ComfyUI / Kilo / image pipeline: not invoked
- Push: no

## Authority transition

The successor identity is accepted and re-frozen for R12D/R12E. R12D
remediation may resume automatically under the standing execution authority.
