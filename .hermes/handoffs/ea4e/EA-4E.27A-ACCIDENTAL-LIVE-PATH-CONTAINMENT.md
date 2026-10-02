# EA-4E.27A Accidental OpenCode Live-Path Containment

Date: 2026-09-06

## Governing State

```text
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=bcf5151464ef9f3bc772b7390eb70e5297f1a8b0
GOVERNING_REMOTE_HEAD=bcf5151464ef9f3bc772b7390eb70e5297f1a8b0
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
STAGED_BEFORE=0
WORKTREE_STATUS_BEFORE=DIRTY_WITH_EXPECTED_EA4E26_EA4E27_AND_UNRELATED_WIP
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
```

## Historical EA-4E.27 Stop

The aborted wider regression is not retroactively classified as passing.

```text
EA4E27_STOP_OCCURRED=YES
EA4E27_FAILED_GATE=NO LIVE ACTIVITY
EA4E27_COMMIT_CREATED=NO
EA4E27_PUSH_PERFORMED=NO
EA4E27_STAGED_FILES=0
EA4E27_TARGETED_TESTS_BEFORE_STOP=106 passed
EA4E27_DEDICATED_TESTS_BEFORE_STOP=24 passed
```

## Accidental Activity Accounting

The first attempted test run collected 34 tests but failed all 34 during fixture setup while trying to remove the real spool directory. It did not enter the executor path. The fixture was then changed to use a temporary directory, but that isolation change did not inject a fake executor. On the second run, 15 static tests passed and the remaining 19 tests entered the real path and failed while polling the shared spool output.

The 19 affected tests were all 16 methods then present in `TestOpenCodeLiveQualification` and all 3 methods then present in `TestOpenCodeActualEventAccounting` in `tests/hermes_core/test_opencode_invocation_authorized_live.py`.

Each of the 19 failure traces reached the following path:

```text
run_opencode_invocation_authorized_live_qualification()
-> RealOpenCodeProductionExecutor.execute()
-> OpenCodeReceiverAdapter.execute()
-> OpenCodeLiveProcess.start()
-> receiver process polling
```

The executor factory constructs one executor per qualification call, the executor makes one adapter call, and the adapter performs one process start before polling. Therefore the 19 stack traces establish 19 instances/calls/start attempts and 19 processes returned from start into polling. They do not establish that an external model completed or returned a response.

```text
ACCIDENTAL_REAL_PATH_CONFIRMED=YES
ACCIDENTAL_PATH_SOURCE_FILE=tests/hermes_core/test_opencode_invocation_authorized_live.py
ACCIDENTAL_PATH_SOURCE_TESTS=19 (16 former TestOpenCodeLiveQualification + 3 former TestOpenCodeActualEventAccounting)
ACCIDENTAL_PATH_SOURCE_FIXTURE=clean_spool_directory; isolated storage only and supplied no fake collaborator
ACCIDENTAL_PATH_SOURCE_SYMBOL=run_opencode_invocation_authorized_live_qualification

REAL_OPENCODE_EXECUTOR_PATH_REACHED=YES
REAL_OPENCODE_ADAPTER_PATH_REACHED=YES
RECEIVER_PROCESS_PATH_REACHED=YES

ACCIDENTAL_TESTS_ENTERING_REAL_PATH=19
ACCIDENTAL_REAL_OPENCODE_EXECUTOR_INSTANTIATIONS=19
ACCIDENTAL_REAL_OPENCODE_EXECUTOR_CALLS=19
ACCIDENTAL_REAL_OPENCODE_ADAPTER_CALLS=19
ACCIDENTAL_RECEIVER_PROCESS_START_ATTEMPTS=19
ACCIDENTAL_RECEIVER_PROCESSES_CONFIRMED_STARTED=19
ACCIDENTAL_MODEL_INVOCATION_ATTEMPTS=19
ACCIDENTAL_MODEL_INVOCATIONS_CONFIRMED=UNCONFIRMED
```

Process inspection during containment showed four identifiable OpenCode desktop processes and two access-restricted OpenCode processes whose executable paths and parents could not be read. No process could be authoritatively tied to the accidental test run, so no ongoing receiver-process count is inferred from that observation.

## Root Cause

```text
ROOT_CAUSE_CLASSIFICATION=LIVE_HARNESS_IMPORTED_AS_NONLIVE + MISSING_FAKE_INJECTION + TEST_NAME_CLASSIFICATION_ERROR
ROOT_CAUSE_FILE=tests/hermes_core/test_opencode_invocation_authorized_live.py
ROOT_CAUSE_SYMBOL=run_opencode_invocation_authorized_live_qualification
ROOT_CAUSE_MECHANISM=19 regression methods directly called the live qualification function, which constructs RealOpenCodeProductionExecutor by default; the autouse fixture only manipulated the real spool directory and never replaced the executor, adapter, or process collaborator
```

The production qualification function explicitly promises one real OpenCode execution. Calling it from a regression run without replacing its terminal executor made the live path reachable by construction. The legacy filename and mixed static/live test classes obscured the selection boundary.

## Fake-Only Remediation

`tests/hermes_core/test_opencode_invocation_authorized_live.py` now declares `NONLIVE_REGRESSION_MODE = "FAKE_ONLY"`. Its autouse fixture:

- injects a deterministic fake executor into the qualification module;
- preserves the canonical executor identity expected by the binding policy;
- returns an execution-spy outcome for existing accounting assertions;
- patches the real executor constructor to raise `NONLIVE_REAL_EXECUTOR_TRIPWIRE`;
- patches `OpenCodeReceiverAdapter.execute()` to raise `NONLIVE_REAL_ADAPTER_TRIPWIRE`;
- patches `OpenCodeLiveProcess.start()` to raise `NONLIVE_PROCESS_START_TRIPWIRE`;
- asserts all three tripwire counters remain zero after every test.

Real-executor identity properties are inspected without constructing a real executor instance. All qualification calls use the deterministic clock. The test class and method names now state that terminal execution and event accounting are fake.

```text
EA4E25_NONLIVE_REGRESSION_REAL_EXECUTOR_REACHABLE=NO
EA4E25_NONLIVE_USES_FAKE_OPENCODE_EXECUTOR=YES
EA4E25_NONLIVE_USES_FAKE_OPENCODE_ADAPTER_OR_EXECUTION_SPY=YES
EA4E25_NONLIVE_REAL_PROCESS_LAUNCH_CAPABLE=NO

NONLIVE_REAL_EXECUTOR_TRIPWIRE_PRESENT=YES
NONLIVE_REAL_ADAPTER_TRIPWIRE_PRESENT=YES
NONLIVE_PROCESS_START_TRIPWIRE_PRESENT=YES
TRIPWIRE_HITS_DURING_CORRECTED_NONLIVE_SUITE=0
```

## Preserved Semantics

The corrected tests continue through the production governance chain through the terminal execution boundary:

```text
router
-> issuance
-> authority validation
-> activation validation
-> EA-4E.21 binding
-> EA-4E.22 resolution
-> EA-4E.23 invocation authorization
-> atomic claim
-> ProductionExecutionBoundary
-> injected fake terminal executor
```

The existing bypass, single-use authorization, second-claim rejection, teardown, no-persistence, no-retry, no-fallback, no-failover, and exact accounting assertions remain active.

```text
EA4E25_GOVERNANCE_PATH_PRESERVED=YES
TESTS_SKIPPED=NO
TESTS_XFAILED=NO
ASSERTIONS_WEAKENED=NO
TEST_MARKER_CLASSIFICATION_INSPECTED=YES
LIVE_TESTS_EXCLUDED_FROM_NONLIVE_SELECTION=YES
NONLIVE_TESTS_PROVABLY_FAKE_ONLY=YES
```

## EA-4E.27 Static State

Static inspection and the 24 dedicated tests confirm that the WIP runtime reads `request.invocation_authorization`, requires it after binding resolution, fails closed when it is missing or invalid, and accepts a valid externally supplied authorization. It does not construct `ProductionInvocationAuthorization` internally.

```text
EA4E27_RUNTIME_NO_LONGER_MANUFACTURES_INVOCATION_AUTH=YES
EA4E27_EXTERNAL_INVOCATION_AUTH_REQUIRED=YES
EA4E27_MISSING_AUTH_FAILS_CLOSED=YES
EA4E27_VALID_EXTERNAL_AUTH_ACCEPTED=YES
```

## Tests

Runtime:

```text
C:\Users\David\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

Results:

```text
EA4E25_CORRECTED_NONLIVE_TESTS=36 passed
EA4E25_CORRECTED_NONLIVE_FAILURES=0
EA4E27_TESTS=24 passed
EA4E27_FAILURES=0

SAFE_NONLIVE_REGRESSION_TOTAL=60 passed
SAFE_NONLIVE_REGRESSION_FAILURES=0

REAL_EXECUTOR_TRIPWIRE_HITS=0
REAL_ADAPTER_TRIPWIRE_HITS=0
PROCESS_START_TRIPWIRE_HITS=0
```

Safe selection classification:

| Suite | Real executor reachable | Real adapter reachable | Process start reachable | Safe |
|---|---|---|---|---|
| `test_opencode_invocation_authorized_live.py` after remediation | No | No | No | Yes |
| `test_governed_production_runtime_27.py` | No; fake executor only | No | No | Yes |

```text
UNRESTRICTED_BROADER_REGRESSION_PERFORMED=NO
BROAD_REGRESSION_SAFE_SELECTION=tests/hermes_core/test_opencode_invocation_authorized_live.py + tests/hermes_core/test_governed_production_runtime_27.py
BROAD_REGRESSION_EXCLUDED_LIVE_CAPABLE_TESTS=all tests/hermes_core files outside the explicit two-file selection were not executed or presumed safe
```

## Frozen Contracts

```text
EA4E23_INVOCATION_CONTRACT_ID=1d34f4c19b6f7e05cd42e6e43dc656e8d2fe8cb53a6187b20ce65983c70243d8
EA4E22_INTEGRATION_CONTRACT_ID=e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a
EA4E21_BINDING_CONTRACT_ID=99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7
EA4E18_INTEGRATION_CONTRACT_ID=d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459
EA4E17_ISSUANCE_CONTRACT_ID=26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78
EA4E14_EXECUTION_CONTRACT_ID=89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6
ALL_FROZEN_CONTRACTS_UNCHANGED=YES
CONTRACT_ROLL_PERFORMED=NO
```

## New Activity During EA-4E.27A

The corrected suite's independent constructor, adapter, and process tripwires all remained at zero. No Kilo, GPU, or ComfyUI path was invoked.

```text
NEW_REAL_OPENCODE_EXECUTOR_CALLS=0
NEW_REAL_OPENCODE_ADAPTER_CALLS=0
NEW_RECEIVER_PROCESS_STARTS=0
NEW_MODEL_INVOCATIONS=0
NEW_KILO_ACTIVITY=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

## Change Scope and Repository Boundary

```text
EA4E27A_MODIFIED_FILES=tests/hermes_core/test_opencode_invocation_authorized_live.py
EA4E27A_CREATED_FILES=.hermes/handoffs/ea4e/EA-4E.27A-ACCIDENTAL-LIVE-PATH-CONTAINMENT.md
EA4E27A_FILE_COUNT=2
EA4E27A_EVIDENCE_CREATED=YES
UNRELATED_WIP_TOUCHED=NO
STAGED=0
COMMIT=NO
PUSH=NO
```

## Final Disposition

```text
EA-4E.27A =
PASS /
ACCIDENTAL REAL OPENCODE PATH ACCOUNTED /
ROOT CAUSE IDENTIFIED /
EA-4E.25 NON-LIVE REGRESSION RESTORED TO STRICT FAKE-ONLY EXECUTION /
REAL EXECUTOR ADAPTER AND PROCESS TRIPWIRES ACTIVE /
NO GOVERNANCE ASSERTIONS WEAKENED /
EA-4E.27 TARGETED TESTS PASS /
SAFE NON-LIVE REGRESSION PASS /
NO NEW REAL RECEIVER ACTIVITY /
CONTRACTS UNCHANGED /
NOT COMMITTED

EA-4E.27 =
HOLD /
READY TO RESUME NON-LIVE QUALIFICATION UNDER SEPARATE CONTINUATION AUTHORIZATION
```
