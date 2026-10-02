# EA-4E.34 Live Restart-Durability Qualification

## Disposition

```text
EA-4E.34 =
HOLD /
PRE-LIVE EXECUTABLE IDENTITY STOP /
NO LIVE AUTHORIZATION ISSUED /
NO AUTHORIZATION CONSUMED /
NO RECEIVER EXECUTED /
NO RETRY REQUIRED OR AUTHORIZED /
NOT COMMITTED

QUALIFIED_RECEIVER=NONE
FAILED_OR_BLOCKED_RECEIVER=kilo-cli-agent
FAILURE_REASON=PINNED_KILO_EXECUTABLE_MISSING
NEXT_REQUIRED_ACTION=SEPARATE NON-LIVE KILO BINARY REQUALIFICATION OR EXACT FROZEN BINARY RESTORATION
```

The qualification stopped before live-store initialization, authorization
issuance, handoff, durable claim, adapter invocation, or receiver process
start. The frozen Kilo executable is absent. EA-4E.34 prohibits executable
substitution and requires an immediate stop when the qualified identity cannot
be used.

## Governing State

Verified in the EA worktree before the live boundary:

```text
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=263258a1d421f5f8d6ca518bfa2fe1afd9079bb5
GOVERNING_REMOTE_HEAD=263258a1d421f5f8d6ca518bfa2fe1afd9079bb5
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
STAGED_BEFORE=0
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
```

The clean qualification source was exported from the governing commit to:

```text
C:\Users\David\AppData\Local\Temp\ea4e34-source-1788781402018
```

This prevented the qualification from importing the unrelated modified
`tools/hermes_core/__init__.py` and
`tools/hermes_core/receiver_registry.py` files in the working tree. Existing
EA-4D.4F artifacts and test-output directories were also left untouched.

## Sealed Contracts

Recomputed from the clean governing source:

```text
EA4E23_CONTRACT_ID=e638e8ff695172eceaf5c36baa1f5063633b32e344971a7d6fc54cf456faff91
EA4E26_CONTRACT_ID=84aad8495a6ec034c763f8c62a98ec41e85ef48c2b453bd098bc3cf57f624a67
EA4E28_CONTRACT_ID=395944480c5ea2cde374b07093f07b6e44633f404abb8e420136ee5516b910e1
EA4E29_CONTRACT_ID=821941da6ea4b08105c359afeb86193e343a429b0a74a32826bd6370faaa5166
SEALED_CONTRACT_CHAIN_RECOMPUTED=YES
SEALED_CONTRACT_CHAIN_MATCHES=YES
```

## Pre-Live Tests

The Codex-bundled Python runtime no longer included working PyYAML/pytest
dependencies. They were installed into the disposable clean-export dependency
folder `.ea4e34-deps`; the shared runtime was not modified.

```text
EA4E34_PREFLIGHT_CONTRACT_TESTS=25 passed
EA4E34_PREFLIGHT_DURABLE_STORE_TESTS=52 passed
EA4E34_PREFLIGHT_PROCESS_GUARD_TESTS=91 passed
EA4E34_PREFLIGHT_FAILURES=0
PREFLIGHT_REAL_RECEIVER_PROCESSES=0
```

Commands used the strict non-live process guard and isolated external pytest
temporary directories.

## Pre-Live Executable Identity

Frozen Kilo identity:

```text
KILO_EXECUTOR_IDENTITY=RealKiloProductionExecutor
KILO_ADAPTER_IDENTITY=KiloAdapter/ea4e.3
AUTHORIZED_KILO_EXECUTABLE=C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.9-win32-x64\bin\kilo.exe
AUTHORIZED_KILO_SHA256=ec8737555947a145f3418962890f539b6b175ba3de125689f7ccb197d0004a36
AUTHORIZED_KILO_VERSION=7.5.9
AUTHORIZED_KILO_EXECUTABLE_PRESENT=NO
```

Installed Kilo extension directories discovered by filesystem inspection only:

```text
C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.14-win32-x64
C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.15-win32-x64
KILO_SUBSTITUTION_ATTEMPTED=NO
KILO_METADATA_PROCESS_STARTED=NO
```

Frozen OpenCode identity was available, but was not used after the Kilo stop:

```text
OPENCODE_EXECUTOR_IDENTITY=RealOpenCodeProductionExecutor
OPENCODE_ADAPTER_IDENTITY=OpenCodeReceiverAdapter/ea4e.2
AUTHORIZED_OPENCODE_EXECUTABLE=C:\Users\David\AppData\Local\hermes\node\node_modules\opencode-ai\bin\opencode.exe
AUTHORIZED_OPENCODE_SHA256=578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35
AUTHORIZED_OPENCODE_VERSION=1.18.11
AUTHORIZED_OPENCODE_EXECUTABLE_PRESENT=YES
ACTUAL_OPENCODE_SHA256=578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35
OPENCODE_EXECUTION_ATTEMPTED=NO
OPENCODE_METADATA_PROCESS_STARTED=NO
```

## Live Store

No live qualification store or anchor was created because executable identity
validation precedes live-state initialization.

```text
EA4E34_STORE_PATH=NOT_CREATED
EA4E34_ANCHOR_PATH=NOT_CREATED
EA4E34_STORE_INITIALIZED_EXPLICITLY=NO_NOT_REACHED
STORE_INSTANCE_ID=NOT_CREATED
INITIAL_STORE_GENERATION=NOT_CREATED
```

## Authorized Tasks

The exact task texts remained frozen but were never handed off:

```text
KILO_AUTHORIZED_TASK_EXACT=Return exactly: EA4E34_KILO_RESTART_DURABILITY_LIVE_OK
KILO_ACTUAL_EXECUTION_TASK=NOT_EXECUTED
KILO_TASK_MUTATED=NO

OPENCODE_AUTHORIZED_TASK_EXACT=Return exactly: EA4E34_OPENCODE_RESTART_DURABILITY_LIVE_OK
OPENCODE_ACTUAL_EXECUTION_TASK=NOT_EXECUTED
OPENCODE_TASK_MUTATED=NO
```

## Live Accounting

```text
KILO_A_AUTHORIZATION_ID=NOT_ISSUED
KILO_B_AUTHORIZATION_ID=NOT_USED
OPENCODE_A_AUTHORIZATION_ID=NOT_ISSUED
OPENCODE_B_AUTHORIZATION_ID=NOT_USED

TOTAL_KILO_REAL_EXECUTOR_CALLS=0
TOTAL_OPENCODE_REAL_EXECUTOR_CALLS=0
TOTAL_KILO_REAL_ADAPTER_CALLS=0
TOTAL_OPENCODE_REAL_ADAPTER_CALLS=0
TOTAL_KILO_RECEIVER_PROCESSES=0
TOTAL_OPENCODE_RECEIVER_PROCESSES=0
TOTAL_KILO_MODEL_INVOCATIONS=0
TOTAL_OPENCODE_MODEL_INVOCATIONS=0
TOTAL_REAL_RECEIVER_EXECUTIONS=0
LIVE_INVOCATION_AUTHS_ISSUED=0
EXTRA_METADATA_ONLY_RECEIVER_PROCESSES=0
UNEXPECTED_PROCESS_STARTS=0
```

Replay and restart checks were not reached because no authorization existed:

```text
KILO_SECOND_CLAIM=NOT_REACHED
KILO_POST_RESTART_REPLAY=NOT_REACHED
OPENCODE_SECOND_CLAIM=NOT_REACHED
OPENCODE_POST_RESTART_REPLAY=NOT_REACHED
LIVE_KILO_AUTH_TO_OPENCODE=NOT_REACHED
LIVE_OPENCODE_AUTH_TO_KILO=NOT_REACHED
KILO_B_USED=NO
OPENCODE_B_USED=NO
```

## Boundaries

```text
AUTOMATIC_RETRY=NO
AUTO_REISSUE_AFTER_FAILURE=NO
FALLBACK=NO
FAILOVER=NO
SCHEDULER_INTEGRATION=NO
CRON_INTEGRATION=NO
APP_PY_INTEGRATION=NO
PERSISTENT_PRODUCTION_ENABLEMENT=NO
GPU_GENERATIONS=0
COMFYUI_CALLS=0
COMMIT=NO
PUSH=NO
UNRELATED_WIP_TOUCHED=NO
```

## Required Follow-Up

EA-4E.34 cannot resume under this packet by substituting Kilo 7.5.14 or 7.5.15.
The next authorization must choose one of two non-live paths:

1. Restore the exact frozen Kilo 7.5.9 executable and verify its expected
   SHA-256 without launching it.
2. Requalify one installed successor Kilo binary, roll the affected sealed
   contracts if their canonical identity changes, and issue a fresh EA-4E.34
   live authorization against that reviewed checkpoint.

No receiver attempt was consumed, so this is a pre-live identity HOLD rather
than a consumed-attempt failure.
