# EA-4D.4F-R12E-R6D Deterministic Lease-Window Remediation

## Disposition

`EA-4D.4F-R12E-R6D IMPLEMENTATION: PASS / READY FOR CLEAN COMMIT`

`R12E-R6D REGRESSION GATE: PASS`

The fixed calendar deadline has been removed from reusable live-proof source.
The replacement is a finite, deterministic policy whose absolute timestamps
are issued once for a fresh governed attempt and replayed without extension.

The temporary regression HOLD caused by replacement of the separately
qualified Codex binary was resolved under the non-live R6E qualification.

## Governing State

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- Starting HEAD: `6646b39946988afe61500ce32a4fe203b8808c19`
- Required parent: `e00780bb16ee13f3bad18501b9cc29d96f8b5f16`
- Frozen R11 SHA-256:
  `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- Runtime namespace contract: `hermes-runtime-namespace/v1`
- Future R6 namespace: `proof-adb795668b3266a8d95572cc`
- Structural schema policy:
  `c1c789f1ceb2c56b324bb4b54f26cf10d83380d5bcb9629b20b6f54ec4470dd3`
- Instance qualification version: `codex-instance-schema-qualification/v1`

## Root Cause

`tests/hermes_core/run_r12e_live_proof.py` defined the reusable module constant:

`DEADLINE = "2026-08-30T23:59:59Z"`

That value was copied into the delegated-task expiry, execution authorization,
claim, execution attempt, worker route, delegated capability lease, mailbox
claim, and result-delivery claim. It was therefore hashed into immutable
authorization and delegation artifacts. On 2026-08-31 the committed source
could only reconstruct expired authority.

The historical HOLD remains correct and unchanged:

- Observed current time: `2026-08-31T13:11:30Z`
- Historical expiry: `2026-08-30T23:59:59Z`
- Lease expired: yes
- Process capability: no

## Qualified Policy

- Policy version: `hermes-live-proof-lease-window/v1`
- Policy ID:
  `63ab96fe12a3206d7ff7f5281b6c0765c9630e394f7c6b3743bce49409a2bc31`
- TTL: `300` seconds
- Maximum permitted TTL: `3600` seconds
- Clock: UTC wall clock
- Serialization: RFC 3339 whole-second UTC with `Z`
- Validity: `issued_at <= now < expires_at`
- Exact expiry: expired
- Clock-skew grace: `0` seconds
- Auto-renewal: no
- Environment override: none
- Caller-provided absolute expiry: not accepted

The five-minute TTL reuses the repository's existing maximum claim lifetime.
It is finite and covers the separately bounded 120-second one-shot process
without introducing a broad authority window.

## Attempt-Bound Issuance And Replay

The future lifecycle is:

1. reserve the source-bound isolated runtime namespace;
2. issue `lease-window.json` once using trusted UTC;
3. derive `expires_at = issued_at + 300 seconds`;
4. freeze the policy, owner, timestamps, and artifact hash;
5. create all authorization/delegation timestamps from that window;
6. reload and compare the same manifest during resume/refreeze/execute;
7. check validity immediately before constructing the process controller.

Exclusive manifest creation prevents competing issuance. Replay loads the
existing manifest and never consults a later clock to create a new expiry.
Restart before expiry recovers the same timestamps. Restart at or after expiry
fails closed and requires a new governed authority boundary.

The attempt-window validity gate is stricter than any older inclusive
`must_start_by` comparison: the process path rejects `now == expires_at`
before process capability.

## Implementation Surface

- `tools/hermes_core/lease_window.py`
- `tests/hermes_core/test_lease_window.py`
- `tests/hermes_core/run_r12e_live_proof.py`
- `tests/hermes_core/test_execution_launch_admission.py`
- this completion record
- `EA-4D.4F-IMPLEMENTATION-CONTINUATION.md`

No R12A-EA-4D.4A-E production authority semantics were changed. The canonical
test-chain helper gained an optional issuance anchor while preserving all
historical defaults for existing callers.

## Verification

Interpreter:
`C:\Users\David\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`

| Gate | Result |
| --- | --- |
| R6D focused lease window | **24 passed, 8 subtests passed** |
| R6C namespace + R6D | **43 passed, 23 subtests passed** |
| R6B instance schema | **26 passed, 3 subtests passed** |
| R12A/B/C focused | **97 passed, 40 subtests passed** |
| Authority/start/routing | **548 passed** |
| Codex adapter / CLI qualification | **92 passed** |
| Complete Hermes Core | **1,325 passed, 104 subtests passed** |

`py_compile` and `git diff --check` passed. All focused and complete regression
gates are green.

## R6E Binary-Hold Resolution

The frozen successor qualification expects:

- version: `codex-cli 0.151.0-alpha.7.1`
- SHA-256:
  `3052f7887c10e97f6cfe4941353bd0763300c4907e49a8688958cb40d4159d89`
- path suffix: `bin/6ca77c4a9caa4eed/codex.exe`
- CLI contract:
  `ae576aea601f46634e6ad0d66b9097f78f157d161fdcd2195be6ad6b0db16495`

That executable remains historical and unavailable. R6E separately qualified:

`C:\Users\David\AppData\Local\OpenAI\Codex\bin\b99306303521e97e\codex.exe`

Replacement identity:

- version: `codex-cli 0.151.0-alpha.7.2`
- size: `313790256` bytes
- SHA-256:
  `bfd4c3b971477a559eadaeae8b1e41382ccb7656bd0104970cf5c6c581f2da7d`
- CLI contract:
  `98cc8fd6a6ffc1bb0bb4a675d5988cc8f4c31960ada4357003980b5d8befec5b`

R6E used only version and parser/help probes. The complete safe ordered argv
was parsed with its stdin marker replaced by `--help`; no task output was
created and no model or agent task was started. The original three binary-pin
failures pass 3/3, and post-suite path/version/SHA revalidation found no drift.

## Capability And Evidence Audit

- Live Codex starts: `0`
- Model invocations: `0`
- Real R6 identities: `0`
- Real R6 namespace created: no
- R6 live budget consumed: no
- R6 remaining: `1`
- Expiry enforcement: yes
- Auto-renewal: no
- Infinite/open-ended lease: no
- Arbitrary expiry override: no
- Generic shell/arbitrary executable: no
- Network/browser/MCP/scheduler/Kilo/GPU/ComfyUI/image-pipeline/RHR action: no

Historical evidence remains unchanged:

- Original R12E evidence:
  `67758d5c5843d8f9a0ffb7fc324e3297244c5af7496bbe3b773817091b380f62`
- R12E-R4 evidence:
  `6bc7af15e81f29a4545dc5557608801a4fa87a2ed6733367012f554a0b59eb0a`

## Boundary

`LEASE EXPIRY ENFORCEMENT: PRESERVED`

`FIXED CALENDAR DEADLINE REUSE: REMOVED`

`ATTEMPT-BOUND BOUNDED LEASE DERIVATION: FOCUSED TESTS PASS`

`CLEAN COMMIT: AUTHORIZED AFTER R6E QUALIFICATION`

`NEXT GATE: FRESH R12E-R6 LIVE AUTHORIZATION / NOT AUTHORIZED`

`FRESH R12E-R6 LIVE AUTHORIZATION: NOT AUTHORIZED`

`PUSH: NO`
