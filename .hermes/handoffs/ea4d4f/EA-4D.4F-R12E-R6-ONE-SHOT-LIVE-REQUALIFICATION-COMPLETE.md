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
