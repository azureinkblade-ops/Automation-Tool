# EA-4D.4F-R12E-R4 One-Shot Live Requalification Complete

## Disposition

`EA-4D.4F-R12E-R4 LIVE REQUALIFICATION: FAIL / TERMINAL`

The single authorized Codex process definitely started. The corrected ordered
CLI contract was accepted far enough to create a Codex thread and begin a turn,
but the request was rejected before model/task execution because the frozen
result schema was invalid for the live response-format validator. No retry is
authorized or attempted.

Earliest failed boundary:

`TRUSTED RESULT SCHEMA ACCEPTANCE`

The service reported `invalid_json_schema`: the
`evidence_manifest.items.properties.evidence_type` schema used `const` without
an explicit `type` key. The same frozen schema also contains other const-only
properties and requires a non-live successor review before any future live
authorization.

## Precheck

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- Starting HEAD: `aa43385d073480add4d6e5ac1fccea1cbb195e6d`
- R12E-R3 parent: `a188c735210d9616d8a6c434f3f441909992f3a0`
- Frozen R11 SHA-256: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- Staged files: `0`
- Tracked modifications: `0`
- Merge/rebase/cherry-pick state: none
- Unrelated untracked R8-R10, pytest, and image-pipeline WIP: preserved and excluded

The exact R12E-R3 commit shape was recovered from Git. It contains only:

- `.hermes/handoffs/ea4d4f/EA-4D.4F-IMPLEMENTATION-CONTINUATION.md`
- `.hermes/handoffs/ea4d4f/EA-4D.4F-R12E-R3-CODEX-ORDERED-ARGV-IMPLEMENTATION-COMPLETE.md`
- `tests/hermes_core/test_codex_adapter.py`
- `tools/hermes_core/codex_adapter.py`

The external Obsidian continuation is a mirror, not a Git artifact.

## New R12E-R4 Identities

- Delegation ID: `delegation-af4df22c4eb350cae42b9c0b6435618253928668215405dbb5703479eeb1dffe`
- Task input hash: `d0116ebcb0bdfe89960a12345871c54d064bb81e76a56112d8ee32f02fd7463c`
- Capability lease ID: `lease-bad90d1e2e974f5c4731641beeb1c345aec320c006ad08d91fda55ed6c9d9267`
- Mailbox delivery ID: `mailmsg-40f059fef2c6d22b9ef5a7e8fc3eefde008d5cfb7a837dcfe862edd5c2184e9c`
- Receiver receipt ID: `receipt-55673edc2323d722b137765962503d93edcc878c4203568ae516169c52c7bc92`
- Authorization ID: `execution-authorization-f311924a0f992d0c`
- Claim ID: `execution-authorization-claim-ad9baac51d0706aa`
- Execution attempt ID: `execution-authorization-attempt-0283e18a1afd25b9`
- Route ID: `3eb21865d2b5643e077db9446c44d3d797427a387845e7f3ce8777433a379e10`
- Launch attempt ID: `latch-3eb21865d2b5643e077db9446c44d3d797427a387845e7f3ce8777433a379e10`
- Invocation/idempotency ID: `8e2ead9147f4afb985113f710f2f107b0450b809480651bd484f411c745706b1`
- Runtime run ID: `codex-run-e5c267fbae2059669f593883a9cc5da9`

All eight principal identity classes checked before launch were distinct. None
reuse the original R12E invocation or delegation lineage.

## Qualified Runtime

- Executable: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe`
- Version: `codex-cli 0.150.0-alpha.12.2`
- Binary SHA-256: `34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f`
- Adapter version: `1.1`
- CLI contract ID: `21f341c1ac959ee3a7c7ce929baf492183bd0d07e7443c0e76e4f22f0196bc02`
- Argv hash: `884c235cfc396e99992f6e5c75930847a7f66df08a0d93604d5efe46dce19e22`
- Input SHA-256: `a61b010163c2569ea9acd3ca7a67e9e954a3bd8ba3df981d0f8ace150b469154`
- Schema SHA-256: `51548a8306b76e273a83f0dfc22c687aae8ede6722d5aa0a4998234983634887`
- Preflight SHA-256: `76f7f406f553751e6e753e7db92b3a438cf97b3d346b18c99ca77f4a8fa23c5f`
- Approval policy: `never`
- Sandbox: `read-only`
- Ambient user config: disabled with `--ignore-user-config`
- Human approval prompts: no
- Arbitrary auto-approval: no
- Dangerous bypass/workspace write: no

The runtime-only R12E-R4 composition harness was hash-frozen in the preflight;
tracked production and test source remained exactly at `aa43385d...`.

## Live Process

- Start classification: `DEFINITELY_STARTED`
- PID: `7196`
- Transport terminal state: `FAILED`
- Exit code: `1`
- Duration: `2.578s`
- Timed out: no
- Cancelled: no
- CLI contract accepted: yes
- Codex thread created: yes, `01a04fca-0198-7c01-92ed-6615d687a344`
- Turn started: yes
- Model/task execution: no; response-format schema validation rejected the request
- Structured terminal result: no
- stdout SHA-256: `f09bcea796d6b73163e58c2eb53f845dc42c7ab6109f63f227ffd370c574db8a`
- stderr SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Evidence SHA-256 before documentation: `6bc7af15e81f29a4545dc5557608801a4fa87a2ed6733367012f554a0b59eb0a`

## Result Return

- Parser: fail; final output was empty
- Schema: fail at live response-format validation
- Evidence validation: not reached
- Output-scope validation: not reached
- Canonical result ID/hash: none
- Result delivery: none
- Originator acknowledgement: none
- Delegation completion projection: none
- Execution projection: none; not reached and not invented

Durable exact replay was exercised with fake process capability after the
terminal failure: it returned `replayed=true`, retained terminal `FAILED`, and
made zero process-start calls. Divergent same-key replay failed closed.

## Tests

Pre-live focused qualification:

- Adapter + process + result store: `110 passed, 6 subtests passed`

Post-live complete Hermes Core regression:

- `1,228 passed, 78 subtests passed`
- Zero failures

The failure is isolated to the live fixture's schema contract. Committed
adapter, transport, delegation, authority, routing, launch, start, and result
store behavior remain regression-clean.

## Accounting

Original R12E remains immutable:

- Authorized: `1`
- Definitive starts: `1`
- Remaining: `0`
- PID: `660`
- Terminal: `FAILED`, exit `2`
- Evidence SHA-256 unchanged: `67758d5c5843d8f9a0ffb7fc324e3297244c5af7496bbe3b773817091b380f62`

R12E-R4:

- Authorized: `1`
- Definitive starts: `1`
- Remaining: `0`
- Second live start: `NO / NOT AUTHORIZED`

## Governance Boundary

```text
ORIGINAL R12E LIVE PROOF=FAIL / TERMINAL / IMMUTABLE
R12E-R1=HOLD
R12E-R2=PASS / SEMANTIC EQUIVALENT FOUND
R12E-R3=PASS / COMMITTED
R12E-R4=FAIL / TERMINAL / SCHEMA ACCEPTANCE
CODEX GOVERNED RECEIVER QUALIFICATION=NOT PASSED
NEXT ACTION=NON-LIVE SCHEMA CONTRACT REMEDIATION REQUIRES NEW AUTHORIZATION
SECOND LIVE START=NO
GENERAL PRODUCTION ACTIVATION=NO
SCHEDULER/DEFAULT COORDINATOR=NO
KILO/GPU/COMFYUI/IMAGE PIPELINE=NO
PUSH=NO
```
