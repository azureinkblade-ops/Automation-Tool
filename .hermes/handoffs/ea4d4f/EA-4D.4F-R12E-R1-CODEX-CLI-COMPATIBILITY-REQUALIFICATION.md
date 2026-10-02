# EA-4D.4F-R12E-R1 Codex CLI Compatibility Requalification

Date: 2026-08-28

## Classification

**CASE B: ARCHITECTURAL INCOMPATIBILITY**

The current Codex CLI version cannot express the frozen R11 approval semantics without changing the authority/security model.

`SEMANTIC_EQUIVALENT_AVAILABLE=NO`

## Frozen R11 Architecture (Section 11.2)

The frozen contract requires:
1. `--sandbox read-only` — read-only sandbox boundary
2. `--ask-for-approval never` — no interactive approval prompts
3. `--disable shell_tool` — no shell execution
4. `--disable browser_use` — no browser automation
5. `--disable image_generation` — no image generation
6. `--disable computer_use` — no computer use
7. `--disable multi_agent` — no multi-agent spawning
8. `--disable plugins` / `--disable hooks` / `--disable apps` — no extensions

## Old Binary (R11 Section 11.2)

- Version: `codex-cli 0.150.0-alpha.8`
- SHA-256: `09d6723925e724edf0bbbbc7b9e204526e0fb1462c86bd2a4997311fd5071eba`
- Path: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\d0097be4feba73d0\codex.exe`
- Old argv form: `codex.exe exec --json --ephemeral --ignore-user-config --ignore-rules --ask-for-approval never --sandbox read-only --disable <capabilities> --cd <dir> -`

## Replacement Binary (qualified in commit 0fe869c)

- Version: `codex-cli 0.150.0-alpha.12.2`
- SHA-256: `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`
- Path: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe`

## Live Evidence of Incompatibility

The failed R12E one-shot live proof (commit d7f7a003) established:
- `START_CLASSIFICATION=DEFINITELY_STARTED`
- `PID=660`
- `EXIT_CODE=2`
- `TERMINAL_STDERR=error: unexpected argument '--ask-for-approval' found`
- `MODEL/TASK_EXECUTION=NOT_REACHED`

The process controller worked exactly as designed. The failure occurred at CLI parsing, before any task was accepted.

## Root Cause: Why Prior Qualification Missed This

The prior binary requalification (commit `0fe869c docs(ea4d4f): requalify Codex binary for R12D`) relied on help-surface inference. It likely inspected the help output of a different version or interpreted the help text incorrectly.

The `--ask-for-approval` flag existed in alpha.8 (the original R11-pinned version) but was **removed** in alpha.12.2. The prior qualification failed to detect this removal because:
1. It relied on non-live CLI help inspection without verifying the actual argv was accepted by the parser
2. It did not run a parser-only validation (e.g., `--help` with the full argv) to confirm acceptance
3. It assumed backward compatibility of CLI flags across versions

## Current CLI Surface (alpha.12.2)

From `codex exec --help`:

**Approval-related flags:**
- `--approve-for-me` — Route approval requests through automatic review using the **workspace-write** sandbox
- `--dangerously-bypass-approvals-and-sandbox` — Skip all confirmation prompts and execute commands **without sandboxing**. EXTREMELY DANGEROUS.

**Sandbox flags:**
- `-s, --sandbox <SANDBOX_MODE>` — possible values: `read-only`, `workspace-write`, `danger-full-access`

**Config flags:**
- `-c, --config <key=value>` — Override a configuration value from `~/.codex/config.toml`
- `--ignore-user-config` — Do not load `$CODEX_HOME/config.toml`

## Semantic Equivalence Analysis

| Frozen R11 Requirement | alpha.12.2 Equivalent | Semantically Equivalent? |
|---|---|---|
| `--ask-for-approval never` | `--dangerously-bypass-approvals-and-sandbox` | **NO** — removes sandbox entirely |
| `--ask-for-approval never` | `--approve-for-me` | **NO** — uses workspace-write sandbox, not read-only |
| `--ask-for-approval never` | `-c approval_policy=never` | **UNKNOWN** — no such config option documented |
| `--sandbox read-only` | `--sandbox read-only` | **YES** — still available |

**Conclusion**: The only alpha.12.2 flag that skips approvals (`--dangerously-bypass-approvals-and-sandbox`) explicitly disables the sandbox. This is NOT semantically equivalent to the frozen R11 requirement of `approval policy = never` WITH `sandbox = read-only`.

The frozen R11 architecture requires BOTH:
1. A read-only sandbox boundary (security isolation)
2. No approval prompts (unattended execution)

alpha.12.2 cannot express both simultaneously. The only way to skip approvals is to also skip sandboxing, which violates the frozen security model.

## Classification: Case B — Architectural Change

This is **Case B** per the R12E-R1 authorization packet:

> "The current Codex version cannot express the frozen approval semantics without changing the authority/security model."

Per authorization:
> "If Case B: HOLD / DESIGN AUTHORITY REQUIRED. Do not self-authorize that redesign."

## Required Governance Action

**HOLD** — Do not attempt a compatibility substitution that weakens the approval requirement.

The proper next governance step is a separately authorized design review to determine:
1. Whether the frozen R11 approval semantics can be preserved with a different Codex version
2. Whether the architecture needs to be updated to reflect the new CLI surface
3. Whether a different receiver agent should be qualified

## Relationship to Frozen R11

- **Frozen R11 architecture unchanged** — The R11 design contract is still authoritative
- **Version-specific Codex CLI invocation material superseded** — The alpha.8-specific argv is no longer valid
- **No successor argv contract qualified** — No alpha.12.2 argv has been proven semantically equivalent

## Supersession Rule

This record supersedes the argv material in:
- `EA-4D.4F-R11-AGENT-TO-AGENT-GOVERNED-DELEGATION-DESIGN.md` Section 11.2 (executable-specific argv)
- `EA-4D.4F-R12D-CODEX-ADAPTER-QUALIFICATION-IMPLEMENTATION-COMPLETE.md` (binary qualification)

The frozen R11 architecture (approval policy = never, sandbox = read-only) remains authoritative.

## Non-Live Inspection Commands Used

```bash
codex.exe exec --help
codex.exe --help
codex.exe debug prompt-input --help
cat ~/.codex/config.toml
```

No model invocation occurred during this investigation.

## Model Execution During Remediation

`MODEL_EXECUTION=NO`

No live Codex process was started during this compatibility investigation.

## Live Accounting (Permanent)

Original R12E:
- `AUTHORIZED=1`
- `DEFINITIVE_STARTS=1`
- `REMAINING=0`

This accounting is permanent for the failed R12E experiment. Do not reset.

## Governance Disposition

```
EA-4D.4F-R12E ORIGINAL LIVE PROOF: FAIL / TERMINAL
EA-4D.4F-R12E-R1: HOLD / ARCHITECTURAL INCOMPATIBILITY
SEMANTIC_EQUIVALENT_AVAILABLE=NO
CODEX CURRENT-BINARY ARGV CONTRACT: NOT REQUALIFIED
SECOND LIVE START: NOT AUTHORIZED
EA-4D.4F-R12E-R2 LIVE REQUALIFICATION: NOT AUTHORIZED (requires design review)
```
