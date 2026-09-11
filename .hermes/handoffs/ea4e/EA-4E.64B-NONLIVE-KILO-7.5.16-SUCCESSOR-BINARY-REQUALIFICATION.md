# EA-4E.64B Non-Live Kilo 7.5.16 Successor Binary Requalification

## Disposition

```ini
EA4E64B_RESULT=PASS
EA4E64B_QUALIFICATION=QUALIFIED_NONLIVE
EA4E64A_HISTORICAL_RESULT=HOLD_UNCHANGED
EA4E64A_STORE_AND_ANCHOR_IMPLEMENTATION=QUALIFIED_NONLIVE
EA4E64A_PERSISTENT_APP_COMPOSITION=QUALIFIED_NONLIVE
EA4E64A_BLOCKING_DOMAIN_CLOSED_BY_EA4E64B=KILO_BINARY_IDENTITY

EA4E64_RETRY_AUTHORIZED=NO
AUTHORIZATION_ISSUED=0
ACTIVATION_AUTH_CLAIMED=0
PRODUCTION_ACTIVATED=NO
RECEIVER_EXECUTED=NO
MODEL_INVOKED=NO
COMMIT=NO
PUSH=NO
```

EA-4E.64B qualified the already-installed Kilo 7.5.16 executable as the
explicit successor to the absent 7.5.15 executable. It did not download,
install, invoke, or implicitly discover a replacement executable. The
historical EA-4E.64A HOLD remains truthful and unchanged.

## Git Preflight

```ini
WORKTREE=C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot
BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_HEAD=6096ee0a79299d7ffaa6e8a17860d930c87e3846
REMOTE_HEAD=6096ee0a79299d7ffaa6e8a17860d930c87e3846
LOCAL_AHEAD=0
LOCAL_BEHIND=0
INITIAL_STAGED=0
CURRENT_WIP_ENTRY_COUNT_AT_START=346
GIT_STATE_REVERIFIED_AT_START=YES
```

No reset, stash, clean, merge, rebase, amend, commit, or push occurred.

## Frozen Invariants

```ini
BINARY_IDENTITY_DISTINCT_FROM_RECEIVER_IDENTITY=YES
BINARY_IDENTITY_DISTINCT_FROM_TRANSPORT_CONTRACT=YES
BINARY_IDENTITY_DISTINCT_FROM_MODEL_BINDING=YES
BINARY_IDENTITY_DISTINCT_FROM_EXECUTOR_BINDING=YES
SUCCESSOR_QUALIFICATION_ISSUES_AUTHORIZATION=NO
SUCCESSOR_QUALIFICATION_ACTIVATES_PRODUCTION=NO
BINDING_PROVISIONING_EXECUTES_RECEIVER=NO
OLD_QUALIFICATION_HISTORY_REWRITTEN=NO
EA4E64B_MASTER_INVARIANTS_PRESERVED=YES
```

## Installed Executable

The executable was read directly from the existing VS Code extension install.
The SHA-256 was recomputed locally. Safe local `--version`, `--help`, and
`run --help` inspection was performed with an isolated local HOME. No task,
message, model, provider, login, browser, or network operation was requested.

```ini
KILO_EXECUTABLE_PATH=C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.16-win32-x64\bin\kilo.exe
KILO_VERSION=7.5.16
KILO_FILE_SIZE=170711552
KILO_SHA256=8ddb47c7ae088c9f2118cec8824d618eea498b3d580970a5f094c7390633a851
KILO_BINARY_HASH_RECOMPUTED=YES
KILO_VERSION_READ_FROM_TRUSTED_LOCAL_SOURCE=YES
KILO_7_5_16_CLI_SURFACE_READABLE=YES
KILO_7_5_16_RECEIVER_INTERFACE_COMPATIBLE=YES
KILO_7_5_15_BINARY_PRESENT=NO
```

The qualified receiver surface remains compatible: positional `run` message,
JSON output selection, pure mode, explicit agent/model selection, ordinary exit
status, and noninteractive operation. The available `--auto` option was not
used and is not admitted by the governed adapter.

## Successor Identity

Historical 7.5.15 identity:

```ini
OLD_KILO_VERSION=7.5.15
OLD_KILO_BINARY_SHA256=78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25
OLD_KILO_TRANSPORT_CONTRACT_ID=d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd
OLD_KILO_EXECUTABLE_BINDING_ID=01274cc23910aebfbbd4666fffea5ce560d80720160a6909e2157576ad177982
OLD_KILO_MODEL_BINDING_ID=b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544
KILO_RECEIVER_ID=kilo-cli-agent
```

Qualified 7.5.16 successor identity:

```ini
NEW_KILO_VERSION=7.5.16
NEW_KILO_BINARY_SHA256=8ddb47c7ae088c9f2118cec8824d618eea498b3d580970a5f094c7390633a851
NEW_KILO_TRANSPORT_CONTRACT_ID=52c828de66703a5ea587e51940dca0ec5c13a92af72b1836e6fc0225a83a5b63
NEW_KILO_EXECUTABLE_BINDING_ID=f681bc8bbfaeca4b3a1199254583f34327ac0de5e12a3ccbc0ff33411eb96563
NEW_KILO_MODEL_BINDING_ID=b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544
KILO_RECEIVER_ID_UNCHANGED=YES
OLD_EXECUTABLE_BINDING_REUSED=NO
MODEL_BINDING_ROLLED=NO
```

## Dependency Analysis

`kilo_adapter._canonical_material` hashes the executable path, SHA-256, and
version into the transport contract. The executable-successor binding then
hashes that transport ID together with the executable identity and stable model
binding. The EA-4E.6 through EA-4E.29 chain transitively seals those values.
The semantic receiver ID and model contract do not include executable identity.

```ini
BINARY_CHANGE_REQUIRES_TRANSPORT_CONTRACT_ROLL=YES
BINARY_CHANGE_REQUIRES_EXECUTABLE_BINDING_ROLL=YES
BINARY_CHANGE_REQUIRES_MODEL_BINDING_ROLL=NO
BINARY_CHANGE_REQUIRES_RECEIVER_ID_ROLL=NO
BINARY_CHANGE_REQUIRES_EXECUTOR_BINDING_ROLL=YES
MODEL_BINDING_CONTAINS_BINARY_IDENTITY=NO
RECEIVER_ID_SEMANTICS_CHANGED=NO
OLD_TRANSPORT_CONTRACT_ID_REUSED_WITH_CHANGED_HASH_INPUT=NO
```

Current transitive contract IDs:

```ini
EA4E6=a80122e6363f67148f9737f096057f2874aa594f04ddb2d18ddab3598fa94c49
EA4E7=05cad9f532b0bc37a5fa28104f72b14a08b53d050c37912f6e367edb22cadfe4
EA4E8=57b48875a3d446e4c2a417975c235c7360d4be6c96b4f0e380965553a126402d
EA4E11=578e0790c6317298d7c81ab5b0ed58e46a197aecdece050ed59c18d9ef29d2d0
EA4E14=ef709f6c2678027f694c3c9a55a498ec973977868428116bfa8b9476118f7f52
EA4E17=62ba7ba5689ff467b8609f924abdf6f1d478a037214dd99c4cbdcccbf6dfbd5b
EA4E18=921ea6c7ce32e57880bd67116e18f943faa66d265f685a9b59d632123c371cb3
EA4E21=eac6a628e11d3d7235e09a2bf745bc2efda9856baf47c432b7ad4813a36691de
EA4E22=93b284477a6f760170058a6ed026592d2238f0a1da7b5905eab8f70c6316eefe
EA4E23=b918118df4b7d72ab632737ce75ca700426e40932cd21a83ead15b3d20ee2319
EA4E26=05880849e3972a5553c2ea7b9ed7e75df33bc8ca3f990df9bf65bc9b15da9891
EA4E28=4b1953dbdf28753a940bb6fed41ea38efd7ed92d657e9d3cdca4b1b760105c88
EA4E29=ac2c38e726a2469b80590f6976acad9a5141e0efb26c2726e342420118ef21f1
```

The complete 7.5.15 chain remains in
`HISTORICAL_EA4E_7_5_15_CONTRACT_IDS`; it is not selectable as the current
chain.

## Persistent Composition Roll

The existing 64A binding descriptor was replaced atomically only after its
exact predecessor binding ID was verified. Provisioning without the explicit
successor flag fails closed with
`PERSISTED_KILO_BINDING_IDENTITY_MISMATCH`. A separate-process reconstruction
then restored the exact new binding ID.

```ini
OLD_PERSISTENT_KILO_EXECUTOR_BINDING_ID=binding-a5fcbadb-b088-4112-a62c-c6e36f3b1e25
NEW_KILO_EXECUTOR_BINDING_REQUIRED=YES
NEW_KILO_EXECUTOR_BINDING_ID=binding-5efe64dc-43e2-4fe2-91bd-12b70bd3326a
NEW_KILO_EXECUTOR_RECEIVER_ID=kilo-cli-agent
NEW_KILO_EXECUTOR_TRANSPORT_CONTRACT_ID=52c828de66703a5ea587e51940dca0ec5c13a92af72b1836e6fc0225a83a5b63
NEW_KILO_EXECUTOR_MODEL_BINDING_ID=b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544
NEW_KILO_EXECUTOR_EXECUTABLE_BINDING_ID=f681bc8bbfaeca4b3a1199254583f34327ac0de5e12a3ccbc0ff33411eb96563
PERSISTENT_APP_COMPOSITION_USES_NEW_KILO_BINDING=YES
NEW_KILO_EXECUTOR_BINDING_SURVIVES_RESTART=YES
NEW_KILO_EXECUTOR_BINDING_ID_STABLE_AFTER_RECONSTRUCTION=YES
NEW_EXECUTOR_BINDING_STARTS_PROCESS=NO
NEW_EXECUTOR_BINDING_INVOKES_MODEL=NO
NEW_EXECUTOR_BINDING_ACTIVATES_PRODUCTION=NO
```

Activation-authority lineage was preserved:

```ini
STORE_ID_BEFORE_KILO_SUCCESSOR_ROLL=activation-store-9a66dfbc-5c7f-4d63-9538-aaf910d76229
STORE_ID_AFTER_KILO_SUCCESSOR_ROLL=activation-store-9a66dfbc-5c7f-4d63-9538-aaf910d76229
STORE_EPOCH_BEFORE_KILO_SUCCESSOR_ROLL=1
STORE_EPOCH_AFTER_KILO_SUCCESSOR_ROLL=1
KILO_BINARY_CHANGE_ROTATES_STORE_ID=NO
KILO_BINARY_CHANGE_ROTATES_STORE_EPOCH=NO
```

The old executor binding is not usable for new issuance. Requests containing
the old runtime binding ID or old transport ID are denied. No alias, fallback,
or implicit substitution exists.

```ini
OLD_KILO_EXECUTOR_BINDING_USABLE_FOR_NEW_ISSUANCE=NO
AUTH_FOR_7_5_15_BINDING_VALID_FOR_7_5_16_BINDING=NO
OLD_TRANSPORT_AUTH_VALID_FOR_NEW_TRANSPORT=NO
OLD_EXECUTABLE_BINDING_AUTH_VALID_FOR_NEW_EXECUTABLE=NO
```

## Prerequisite Recheck

```ini
EA4E64_PREFLIGHT_STORE_READY=YES
EA4E64_PREFLIGHT_EXTERNAL_ANCHOR_READY=YES
EA4E64_PREFLIGHT_APP_COMPOSITION_READY=YES
EA4E64_PREFLIGHT_KILO_EXECUTOR_BINDING_READY=YES
EA4E64_PREREQUISITES_CLOSED=YES
AUTHORIZATION_ISSUED=0
```

## Tests

All tests used the pre-existing stage-2 Python runtime. No package was added or
updated.

```ini
PYTEST_RUNTIME=C:\Users\David\Documents\Automation tool\.venv-stage2-v2\Scripts\python.exe

EA4E64B_DEDICATED_TEST_FILE=tests/hermes_core/test_ea4e64b_nonlive_kilo_7_5_16_successor.py
EA4E64B_DEDICATED_TESTS_COLLECTED=17
EA4E64B_DEDICATED_TESTS_PASSED=17
EA4E64B_DEDICATED_TESTS_FAILED=0

KILO_ADAPTER_RECEIVER_BINDING_REGRESSION_COLLECTED=256
KILO_ADAPTER_RECEIVER_BINDING_REGRESSION_PASSED=256
KILO_ADAPTER_RECEIVER_BINDING_REGRESSION_FAILED=0

EA4E64A_DEDICATED_REGRESSION_COLLECTED=16
EA4E64A_DEDICATED_REGRESSION_PASSED=16
EA4E64A_DEDICATED_REGRESSION_FAILED=0

EA4E62B_REGRESSION_COLLECTED=57
EA4E62B_REGRESSION_PASSED=57
EA4E62B_REGRESSION_FAILED=0

PREDECESSOR_TEST_COUNT_DERIVED_FROM_PYTEST_COLLECTION=YES
PREDECESSOR_TESTS_COLLECTED=191
PREDECESSOR_TESTS_PASSED=191
PREDECESSOR_TESTS_FAILED=0
PREDECESSOR_COLLECTION_REQUIRES_UNTRACKED_DEPENDENCY=NO

SEALED_ALIGNED_TESTS_COLLECTED=171
SEALED_ALIGNED_PASSED=171
SEALED_ALIGNED_FAILED=0

BROADER_COMPATIBILITY_PASSED=3196
BROADER_COMPATIBILITY_FAILED=40
BROADER_COMPATIBILITY_SUBTESTS_PASSED=104
BROADER_COMPATIBILITY_FAILURES_INHERITED=40
BROADER_COMPATIBILITY_NEW_FAILURES=0
```

The 40 broader failures are outside 64B and remain visible:

- three missing historical Codex-binary qualification fixtures;
- inherited dual-receiver tests that conflict with the one-binding limit;
- inherited fake paths that omit the durable invocation-authorization store;
- one inherited feature-gate fixture;
- one missing historical OpenCode replay spool artifact.

The first full run exposed stale current-chain assertions in older Kilo and
OpenCode compatibility tests. After those assertions were rolled, no 64B
contract failure remained. The final elevated broad run also proved the local
Kilo version check and avoided the prior sandbox-only OpenCode spool cleanup
errors.

## Bounded Remediation

```ini
INLINE_REMEDIATION_REQUIRED=YES
INLINE_REMEDIATION_COUNT=2
INLINE_REMEDIATION_1=WINDOWS_ECHO_FIXTURE_USED_A_SHELL_BUILTIN_WITH_SHELL_FALSE
INLINE_REMEDIATION_2=OLDER_CURRENT_CHAIN_ASSERTIONS_PINNED_PRE_SUCCESSOR_IDS
PREVIOUS_SECURITY_ASSERTIONS_REMOVED_TO_FORCE_PASS=NO
PREVIOUS_GOVERNANCE_ASSERTIONS_WEAKENED=NO
POST_REMEDIATION_FULL_REQUALIFICATION=PASS_WITH_40_INHERITED_BROADER_FAILURES_AND_0_NEW_FAILURES
```

The Windows fixture correction changed `echo hello` to explicit
`cmd /d /c echo hello`. Historical contract IDs remain asserted separately;
only assertions explicitly representing the current chain were updated.

## Static Safety

Compilation, import, diff validation, and an added-line capability scan passed.
The successor implementation added no process start, model call, network call,
provider call, browser/login flow, download/install path, automatic issuance,
automatic activation, fallback executable discovery, or automatic failover.

```ini
PROHIBITED_RUNTIME_CAPABILITY_SCAN=PASS
IF_QUALIFIED_BINARY_MISSING_USE_ANY_INSTALLED_KILO=NO
IF_QUALIFIED_BINARY_HASH_MISMATCH_USE_NEWEST_KILO=NO
IF_EXECUTOR_BINDING_MISSING_AUTO_REBIND=NO
IMPORT_SUCCESSOR_MODULE_STARTS_KILO=NO
IMPORT_SUCCESSOR_MODULE_INVOKES_MODEL=NO
IMPORT_SUCCESSOR_MODULE_CALLS_NETWORK=NO
APP_COMPOSITION_BUILD_STARTS_KILO=NO
APP_COMPOSITION_BUILD_INVOKES_MODEL=NO
APP_COMPOSITION_BUILD_ISSUES_ACTIVATION_AUTH=NO
NETWORK_CALLS=0
DOWNLOADS=0
PACKAGE_INSTALLS=0
PACKAGE_UPDATES=0
```

One Kilo process existed both before and after the composition roll: PID 17612,
the pre-existing VS Code Kilo `serve --port 0` process. EA-4E.64B started no
additional Kilo process and did not interact with that process.

## Change Ownership

EA-4E.64A deployment-composition WIP retained:

- `app.py`
- `tools/hermes_core/production_app_config.py`
- `tools/hermes_core/production_app_factory.py`
- `tools/hermes_core/production_executor_binding.py`
- `tools/hermes_core/production_wiring.py`
- `tools/hermes_core/production_deployment_composition.py`
- `tests/hermes_core/test_ea4e64a_nonlive_deployment_composition.py`
- `.hermes/handoffs/ea4e/EA-4E.64A-NONLIVE-DEPLOYMENT-COMPOSITION-QUALIFICATION.md`

EA-4E.64B successor changes:

- `tools/hermes_core/kilo_adapter.py`
- `tools/hermes_core/kilo_successor_binding.py`
- `tools/hermes_core/production_credential_preflight.py`
- `tools/hermes_core/production_deployment_composition.py`

EA-4E.64B tests and current-chain expectation updates:

- `tests/hermes_core/test_ea4e64b_nonlive_kilo_7_5_16_successor.py`
- `tests/hermes_core/test_ea4e34b_kilo_successor_contract_roll.py`
- `tests/hermes_core/test_ea4e31_restart_durability_contracts.py`
- `tests/hermes_core/test_ea4e32_restart_durable_authorization.py`
- `tests/hermes_core/test_ea4e33a_store_rollback_detection.py`
- `tests/hermes_core/test_ea4e33_operational_safety.py`
- `tests/hermes_core/test_kilo_adapter.py`
- `tests/hermes_core/test_kilo_invocation_authorized_live.py`
- `tests/hermes_core/test_opencode_invocation_authorized_live_25ra.py`

EA-4E.64B evidence:

- `.hermes/handoffs/ea4e/EA-4E.64B-NONLIVE-KILO-7.5.16-SUCCESSOR-BINARY-REQUALIFICATION.md`

Pre-existing protected tracked changes were not modified by 64B:

- `.hermes/handoffs/ea4e/EA-4E.6-RECEIVER-ROUTER-FAKE-QUALIFICATION.md`
- `tools/hermes_core/__init__.py`
- `tools/hermes_core/receiver_registry.py`

Unrelated untracked files, pytest directories, Studio Bible/image-pipeline WIP,
and self-improvement material were not deleted, staged, or modified.

```ini
CURRENT_WIP_ENTRY_COUNT_AFTER_QUALIFICATION=371
PREEXISTING_TRACKED_SOURCE_CHANGES_TOUCHED=NO
UNRELATED_WIP_TOUCHED=NO
AMBIGUOUS_FILES=NONE_IN_64A_64B_CHECKPOINT_CANDIDATE
FINAL_STAGED=0
COMMIT=NO
PUSH=NO
```

## Live Counters

```ini
AUTHORIZATION_ISSUED=0
ACTIVATION_AUTH_CLAIMED=0
PRODUCTION_ACTIVATED=NO

KILO_TASKS=0
KILO_RECEIVER_PROCESSES_STARTED=0
KILO_MODEL_INVOCATIONS=0

OPENCODE_TASKS=0
OPENCODE_RECEIVER_PROCESSES_STARTED=0
OPENCODE_MODEL_INVOCATIONS=0

NETWORK_CALLS=0
PROVIDER_API_CALLS=0
DEVICE_CODE_FLOWS_STARTED=0
OAUTH_FLOWS_STARTED=0
BROWSERS_OPENED=0
CREDENTIALS_CREATED=0
CREDENTIALS_UPDATED=0
CREDENTIALS_DELETED=0
```

EA-4E.64B ends at the authorized non-live boundary. A clean-commit review and
any EA-4E.64 retry or real authorization issuance require separate authority.
