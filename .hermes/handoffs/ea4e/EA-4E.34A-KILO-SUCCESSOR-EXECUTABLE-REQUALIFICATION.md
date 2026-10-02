# EA-4E.34A Kilo Successor Executable Requalification

## Disposition

```text
EA-4E.34A =
HOLD /
KILO SUCCESSOR REQUIRES SEPARATE CONTRACT-ROLL GOVERNANCE /
NO PRODUCTION CHANGE /
NO REAL RECEIVER OR MODEL EXECUTION /
NOT COMMITTED

SELECTED_CANDIDATE=Kilo 7.5.15
AFFECTED_CONTRACTS=Kilo transport; EA-4E.6, .7, .8, .11, .14, .17, .18, .21, .22, .23, .26, .28, .29; EA-4E.34 live configuration
NEXT_REQUIRED_ACTION=AUTHORIZE A NON-LIVE KILO 7.5.15 TRANSPORT AND DOWNSTREAM SEALED-CONTRACT ROLL
```

The selected executable has a different path, version, size, and SHA-256 from
the historical Kilo 7.5.9 executable. Those fields are canonical Kilo
transport material, so the successor cannot be accepted under the frozen
transport ID. EA-4E.34A requires an immediate stop when a transport or
downstream contract roll is required.

## Governing State

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

The analysis used the clean source export of the governing commit at:

```text
C:\Users\David\AppData\Local\Temp\ea4e34-source-1788781402018
```

Existing modified and untracked worktree files were not imported or changed.

## Preserved EA-4E.34 History

```text
EA4E34_PRIOR_RESULT=HOLD
EA4E34_PRIOR_REASON=FROZEN_KILO_7_5_9_EXECUTABLE_MISSING
EA4E34_PRIOR_LIVE_AUTHS=0
EA4E34_PRIOR_RECEIVER_EXECUTIONS=0
EA4E34_PRIOR_MODEL_INVOCATIONS=0
```

The prior HOLD remains recorded in
`EA-4E.34-LIVE-RESTART-DURABILITY-QUALIFICATION.md` and was not rewritten.

## Sealed Contract Chain

Recomputed from the clean governing source before candidate analysis:

```text
EA4E23=e638e8ff695172eceaf5c36baa1f5063633b32e344971a7d6fc54cf456faff91
EA4E26=84aad8495a6ec034c763f8c62a98ec41e85ef48c2b453bd098bc3cf57f624a67
EA4E28=395944480c5ea2cde374b07093f07b6e44633f404abb8e420136ee5516b910e1
EA4E29=821941da6ea4b08105c359afeb86193e343a429b0a74a32826bd6370faaa5166
SEALED_CONTRACT_CHAIN_RECOMPUTED=YES
SEALED_CONTRACT_CHAIN_MATCHES=YES
```

## Historical Kilo Binding

Retrieved from `kilo_adapter.py`, `receiver_router.py`,
`production_executor_binding.py`, and the frozen EA-4E evidence:

```text
FROZEN_KILO_RECEIVER_ID=kilo-cli-agent
FROZEN_KILO_EXECUTABLE_VERSION=7.5.9
FROZEN_KILO_EXECUTABLE_PATH=C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.9-win32-x64\bin\kilo.exe
FROZEN_KILO_EXECUTABLE_SHA256=ec8737555947a145f3418962890f539b6b175ba3de125689f7ccb197d0004a36
FROZEN_KILO_EXECUTOR_IDENTITY=RealKiloProductionExecutor
FROZEN_KILO_ADAPTER_IDENTITY=KiloAdapter/ea4e.3
FROZEN_KILO_TRANSPORT_CONTRACT_ID=c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500
FROZEN_KILO_MODEL_BINDING_ID=b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544
KILO_7_5_9_BINDING_PRESERVED_HISTORICALLY=YES
KILO_7_5_9_MARKED_UNAVAILABLE=YES
```

## Candidate Inventory

Candidate 7.5.14:

```text
VERSION=7.5.14
PATH=C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.14-win32-x64\bin\kilo.exe
FILE_EXISTS=YES
FILE_SIZE=170643968
SHA256=e50de58f8e5da13cb2ab52a877731665424e95d8a6fed76dcd62f8df4ab8c0f9
SIGNATURE_OR_PACKAGE_METADATA=Authenticode NotSigned; package kilo-code 7.5.14; publisher kilocode; VS Code engine ^1.105.1
CANDIDATE_7_5_14_STATUS=NOT_SELECTED_OBSOLETE
```

Candidate 7.5.15:

```text
VERSION=7.5.15
PATH=C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.15-win32-x64\bin\kilo.exe
FILE_EXISTS=YES
FILE_SIZE=170690048
SHA256=78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25
SIGNATURE_OR_PACKAGE_METADATA=Authenticode NotSigned; package kilo-code 7.5.15; publisher kilocode; VS Code engine ^1.105.1
CANDIDATE_7_5_15_STATUS=SELECTED_ACTIVE_INSTALLED_SUCCESSOR
```

Local VS Code extension metadata marks
`kilocode.kilo-code-7.5.14-win32-x64` obsolete. It does not mark 7.5.15
obsolete. No package was downloaded or installed.

## Selection

```text
SELECTED_SUCCESSOR_VERSION=7.5.15
SELECTED_SUCCESSOR_PATH=C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.15-win32-x64\bin\kilo.exe
SELECTED_SUCCESSOR_SHA256=78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25
SELECTION_RATIONALE=7.5.15 is the active installed stable package; 7.5.14 is locally marked obsolete
```

Exactly one candidate progressed to impact analysis.

## Static Adapter Compatibility Review

The repository's current adapter fixes this invocation shape:

```text
<kilo executable> run --format json --pure --agent hermes-ea4e-kilo-receiver --model <frozen model> <task>
```

The locally packaged changelog between the frozen and successor versions does
not declare a change to this command, positional task delivery, JSONL output,
exit behavior, timeout behavior, or environment handling. That is supporting
static evidence only; candidate behavior was not executed under this phase.

```text
CLI_INVOCATION_SHAPE_COMPATIBLE=EXPECTED_YES_STATIC_ONLY_NOT_QUALIFIED
STDIN_STDOUT_CONTRACT_COMPATIBLE=EXPECTED_YES_STATIC_ONLY_NOT_QUALIFIED
EXIT_CODE_SEMANTICS_COMPATIBLE=EXPECTED_YES_STATIC_ONLY_NOT_QUALIFIED
TIMEOUT_SEMANTICS_COMPATIBLE=EXPECTED_YES_STATIC_ONLY_NOT_QUALIFIED
WORKDIR_SEMANTICS_COMPATIBLE=EXPECTED_YES_ADAPTER_OWNED_NOT_QUALIFIED
ENVIRONMENT_SEMANTICS_COMPATIBLE=EXPECTED_YES_ADAPTER_OWNED_NOT_QUALIFIED
OUTPUT_CAPTURE_SEMANTICS_COMPATIBLE=EXPECTED_YES_STATIC_ONLY_NOT_QUALIFIED
```

These observations are insufficient to preserve the old transport contract
because executable identity is explicitly part of that contract.

## Contract Impact

The static impact computation ran with `subprocess.Popen` and
`subprocess.run` replaced by deny guards. It changed only in-process canonical
material and did not alter repository files or launch Kilo.

```text
OLD_KILO_TRANSPORT_CONTRACT_ID=c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500
PROVISIONAL_7_5_15_TRANSPORT_CONTRACT_ID=6ebff3dfdfc9f9125b94332f95b7559e38d756602b0d6eeefcbb23dd56279749
KILO_TRANSPORT_CONTRACT_CHANGE_REQUIRED=YES
KILO_MODEL_BINDING_CHANGE_REQUIRED=NO
SEALED_CONTRACT_DEFECT_FOUND=NO
```

The provisional ID proves that changing the path, SHA-256, and version changes
the contract. It is not a qualified replacement contract: a proper contract
roll must also review and update all canonical source-provenance fields rather
than treating this calculation as the final successor artifact.

The repository has no separate durable executable-binding artifact independent
of the transport contract. Executable path/version/SHA-256 and the isolation
PATH are embedded in the transport material.

```text
KILO_EXECUTABLE_BINDING_PRESENT=NO_DISTINCT_BINDING
OLD_KILO_EXECUTABLE_BINDING_ID=EMBEDDED_IN_c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500
NEW_KILO_EXECUTABLE_BINDING_ID=REQUIRES_CONTRACT_ROLL
OLD_AND_NEW_EXECUTABLE_IDENTITY_DISTINCT=YES
```

## Downstream Impact Graph

```text
EA-4E.6=directly embeds qualified Kilo transport ID in receiver routing
EA-4E.7=embeds receiver/router authority material
EA-4E.8=embeds qualified receiver and dispatch material
EA-4E.11=embeds qualified receiver activation material
EA-4E.14=embeds EA-4E.6, .7, .11 and qualified receiver transport material
EA-4E.17=embeds EA-4E.6, .7, .11, .14 and qualified receiver transport material
EA-4E.18=embeds EA-4E.6, .7, .11, .14, .17 and qualified receiver transport material
EA-4E.21=directly embeds qualified Kilo transport ID
EA-4E.22=embeds EA-4E.14, .17, .18, .21 and qualified receiver transport IDs
EA-4E.23=embeds EA-4E.14, .18 and sealed EA-4E.17, .21, .22 identities
EA-4E.26=embeds EA-4E.14, .17, .18, .21, .22, .23 and qualified receiver transport IDs
EA-4E.28=embeds EA-4E.21, EA-4E.22 and EA-4E.23
EA-4E.29=embeds EA-4E.22, EA-4E.26 and EA-4E.28
EA-4E.34=must pin the reviewed successor executable and rolled chain

DOWNSTREAM_DEPENDENCIES_AFFECTED=EA-4E.6, EA-4E.7, EA-4E.8, EA-4E.11, EA-4E.14, EA-4E.17, EA-4E.18, EA-4E.21, EA-4E.22, EA-4E.23, EA-4E.26, EA-4E.28, EA-4E.29, EA-4E.34
DOWNSTREAM_CONTRACT_ROLL_REQUIRED=YES
```

## Test and Successor-Artifact Status

The transport-impact gate required stopping before test-only successor
injection, fake execution regression, durability regression, rollback
regression, or artifact creation.

```text
SUCCESSOR_IDENTITY_TEST_INJECTION=NOT_IMPLEMENTED_STOP_CONDITION_REACHED
PRODUCTION_AUTO_SUBSTITUTION=NO
PRODUCTION_SELECTS_LATEST_INSTALLED_KILO=NO
PRODUCTION_AUTOMATIC_VERSION_FALLBACK=NO
PRODUCTION_EXECUTABLE_SUBSTITUTION=NO
PRODUCTION_KILO_BINDING_UPDATED=NO
LIVE_KILO_ENABLED=NO

KILO_ADAPTER_FAKE_TESTS=NOT_RUN_STOP_AT_TRANSPORT_CONTRACT_IMPACT_GATE
KILO_EXECUTION_BOUNDARY_FAKE_TESTS=NOT_RUN_STOP_AT_TRANSPORT_CONTRACT_IMPACT_GATE
EA4E21_KILO_SAFE_TESTS=NOT_RUN_STOP_AT_TRANSPORT_CONTRACT_IMPACT_GATE
EA4E22_KILO_SAFE_TESTS=NOT_RUN_STOP_AT_TRANSPORT_CONTRACT_IMPACT_GATE
EA4E23_KILO_SAFE_TESTS=NOT_RUN_STOP_AT_TRANSPORT_CONTRACT_IMPACT_GATE
EA4E26_KILO_SAFE_TESTS=NOT_RUN_STOP_AT_TRANSPORT_CONTRACT_IMPACT_GATE
EA4E28_KILO_SAFE_TESTS=NOT_RUN_STOP_AT_TRANSPORT_CONTRACT_IMPACT_GATE
EA4E29_KILO_SAFE_TESTS=NOT_RUN_STOP_AT_TRANSPORT_CONTRACT_IMPACT_GATE
FINAL_SAFE_NONLIVE_TEST_TOTAL=0_NOT_REACHED
FINAL_SAFE_NONLIVE_SUBTEST_TOTAL=0_NOT_REACHED
FINAL_SAFE_NONLIVE_FAILURES=0_NOT_RUN

SUCCESSOR_AUTH_ISSUANCE_DURABLE=NOT_TESTED_STOP_CONDITION_REACHED
SUCCESSOR_AUTH_CONSUMPTION_DURABLE=NOT_TESTED_STOP_CONDITION_REACHED
SUCCESSOR_POST_RESTART_REPLAY_DENIED=NOT_TESTED_STOP_CONDITION_REACHED
SUCCESSOR_CROSS_RECEIVER_REPLAY_DENIED=NOT_TESTED_STOP_CONDITION_REACHED
SUCCESSOR_STALE_BACKUP_REPLAY_DENIED=NOT_TESTED_STOP_CONDITION_REACHED
SUCCESSOR_VALID_DB_REPLACEMENT_DETECTED=NOT_TESTED_STOP_CONDITION_REACHED
SUCCESSOR_DB_ANCHOR_MISMATCH_FAILS_CLOSED=NOT_TESTED_STOP_CONDITION_REACHED

SELECTED_SUCCESSOR_RECEIVER_ID=kilo-cli-agent
SUCCESSOR_EXECUTOR_IDENTITY=RealKiloProductionExecutor
SUCCESSOR_EXECUTOR_IDENTITY_DETERMINISTIC=YES_AT_CLASS_LEVEL_BINARY_BINDING_NOT_YET_QUALIFIED
SUCCESSOR_BINDING_ARTIFACT_ID=NOT_CREATED_CONTRACT_ROLL_REQUIRED
```

No assertions were weakened and no production behavior was changed.

## Process Accounting

```text
PROCESS_LAUNCHES_FOR_CANDIDATE_DISCOVERY=0
OPENCODE_BINARY_PROCESSES=0
KILO_BINARY_PROCESSES=0
CODEX_BINARY_PROCESSES=0
RECEIVER_PROCESSES=0
MODEL_INVOCATIONS=0
BLOCKED_PROCESS_ATTEMPTS=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

## Repository Boundary

```text
EA4E34A_EVIDENCE_CREATED=YES
UNRELATED_WIP_TOUCHED=NO
STAGED=0
COMMIT=NO
PUSH=NO
```

EA-4E.34 remains on HOLD. No live qualification may resume until a separately
authorized non-live phase rolls and requalifies the Kilo 7.5.15 transport and
all affected downstream sealed contracts, followed by a reviewed checkpoint.
