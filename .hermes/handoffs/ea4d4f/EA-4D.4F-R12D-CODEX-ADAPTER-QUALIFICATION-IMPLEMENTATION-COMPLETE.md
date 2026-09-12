# EA-4D.4F-R12D Codex Adapter Qualification Implementation Complete

Date: 2026-08-29

## Final state

`EA-4D.4F-R12D IMPLEMENTATION: COMPLETE / NOT COMMITTED`

- R11 architecture: unchanged and frozen at
  `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`.
- R12A: committed at `025bfe33a7229b044ba421469a7516166fffeda1`.
- R12B: committed at `e7b42eac2931f20a400092b3b5fa8d7323557714`.
- R12C: committed at `23023ae91dd6a464b985b1d171afd1aa0aca00b8`.
- Codex binary successor qualification: committed at
  `0fe869c94635beb4d26acb570694f86ebdfa47c0`.
- R12E live proof: authorized under the standing packet but not started.
- Push: no.

## Implementation surface

Production:

- `tools/hermes_core/codex_adapter.py`

Tests:

- `tests/hermes_core/test_codex_adapter.py`

Governance:

- `.hermes/handoffs/ea4d4f/EA-4D.4F-R12D-CODEX-ADAPTER-QUALIFICATION-IMPLEMENTATION-COMPLETE.md`
- `.hermes/handoffs/ea4d4f/EA-4D.4F-IMPLEMENTATION-CONTINUATION.md`

No EA-4D.4A-E production module was modified.

## Binary binding

The adapter verifies the actual executable bytes and runs one bounded
metadata-only `--version` process against the same absolute path with
`shell=False`. It fails closed before any delegated workload on a missing file,
hash mismatch, probe failure, or version mismatch.

- Canonical path:
  `C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe`
- Version: `codex-cli 0.150.0-alpha.12.2`
- SHA-256: `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`
- File size: `310753072` bytes
- Successor qualification:
  `.hermes/handoffs/ea4d4f/EA-4D.4F-CODEX-BINARY-REQUALIFICATION.md`

Bare executable names and PATH lookup are not accepted.

## Trusted invocation policy

`CodexTrustedConfig` owns the exact executable, fixture root, cwd, output
schema, output spool, registry, environment allowlist, and timeout. Delegated
task data can enter only through bounded stdin.

- structured argv and `shell=False`;
- ordinary Windows backslashes and spaces remain valid argv data;
- cwd/schema/spool/registry must resolve inside the trusted fixture root;
- PATH is not inherited;
- timeout is explicitly bounded from 5 through 300 seconds, default 60;
- output schema and final-message spool are adapter-owned paths;
- all frozen execution/browser/image/plugin/multi-agent capabilities are
  disabled in argv.

## Durable replay and cancellation

The adapter owns a separate SQLite transport registry, schema version 1. It is
not Hermes governance authority and cannot project task state.

- `runtime_run_id` is persisted before fake spawn and remains distinct from
  delegation, authorization, execution-attempt, launch, receipt, and result
  identities;
- exact replay returns the existing transport identity/result;
- divergent same-key replay raises a typed conflict;
- PREPARED replay may perform the first start;
- FAILED_BEFORE_START, UNKNOWN, DEFINITELY_STARTED, and terminal replay never
  trigger a blind second process;
- a captured terminal result is reconstructed and reverified after adapter
  reconstruction;
- cancellation/revocation before start prevents spawn;
- durable cancellation after a definite fake start is observed from the
  registry and causes bounded terminate/kill through the Codex-specific process
  protocol;
- timeout also uses bounded terminate/kill and never retries automatically.

## Structured result contract

The minimal pinned JSONL parser accepts only the reviewed event family, enforces
thread/turn/item ordering, requires exactly one last terminal event, and rejects
unknown events, malformed/truncated streams, incompatible required fields, and
bounded-output violations.

The final output must exactly match the pinned result shape. A zero process exit
without valid JSONL and final structured output is not verified. A nonzero
process with a valid PID remains `DEFINITELY_STARTED`; process start and process
success are not collapsed. A valid terminal artifact captured with a nonzero
exit remains available as evidence while the invocation failure stays visible.

## Corrections made during remediation

1. The initial identity helper merely echoed trusted constants. It now hashes
   the real file, probes the real version, and binds the exact verified path.
2. The original argv accepted caller cwd/environment and rejected Windows
   backslashes. Trusted configuration now owns launch structure and relies on
   structured argv rather than shell-character heuristics.
3. The original timeout accepted arbitrary values. Explicit bounds now fail
   closed.
4. The original cancellation and replay structures did not govern behavior.
   The SQLite transport registry and fake-process lifecycle now enforce them.
5. The original parser accepted an invented loose event contract. The current
   parser validates the reviewed JSONL event family and final output separately.
6. The original start classifier called a nonzero process with a PID
   `FAILED_BEFORE_START`. It now preserves definitive start evidence.
7. Focused testing found that SQLite context managers on Windows did not close
   registry handles. Production registry connections now close explicitly.
8. The schema-tamper test initially repeated that same fixture mistake. Its
   deliberate mutation now commits and closes before verification.

## Verification

Interpreter:

`C:\Users\David\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

| Gate | Result |
|---|---|
| R12D focused | 64 passed |
| R12C focused | 9 passed |
| R12B focused | 38 passed, 25 subtests |
| R12A focused | 50 passed, 15 subtests |
| Authority/attempt/routing/launch/start ladder | 548 passed |
| Complete Hermes Core final rerun | 1,182 passed, 72 subtests |

## Capability audit

AST/callsite inspection found:

- prohibited imports: zero;
- `subprocess.Popen`: zero;
- generic shell/system calls: zero;
- `shell=True`: zero;
- network/browser/MCP/GPU/ComfyUI/Kilo/image-pipeline/scheduler capability:
  zero;
- `subprocess.run`: exactly one call, confined to the absolute-path
  metadata-only `--version` probe with `shell=False` and a 10-second timeout.

No live Codex model/agent task, prompt, `codex exec`, Kilo call, browser action,
GPU action, or ComfyUI action occurred.

## R12E accounting

- `R12E_AUTHORIZED_LIVE_INVOCATIONS=1`
- `R12E_DEFINITIVE_STARTS=0`
- `R12E_REMAINING=1`

R12D may be committed after the final full-suite and changed-set gates pass.
After that clean commit, the standing authority advances automatically to the
frozen one-shot R12E proof.
