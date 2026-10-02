# EA-4E.33B OpenCode Process-Probe Incident Requalification

## Governing State

```text
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=fe3f4c0eb9cfe38ac1d7b62ee789be5e2de8eb14
GOVERNING_REMOTE_HEAD=fe3f4c0eb9cfe38ac1d7b62ee789be5e2de8eb14
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
STAGED_BEFORE=0
WORKTREE_STATUS_BEFORE=DIRTY_WITH_EXPECTED_EA4E30_33A_AND_UNRELATED_WIP
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
```

## Historical Incident

EA-4E.33A's initial qualification remains recorded as a hold. Its eight
OpenCode metadata process starts are not rewritten or normalized by this
requalification.

```text
EA4E33A_PRIOR_RESULT=HOLD
EA4E33A_PRIOR_PROCESS_BOUNDARY_VIOLATION=YES
EA4E33A_PRIOR_OPENCODE_VERSION_PROBES=8
EA4E33A_PRIOR_TASKS=0
EA4E33A_PRIOR_MODELS=0
EA4E33A_PRIOR_ADAPTER_EXECUTIONS=0
EA4E33A_PRIOR_PRODUCTION_EXECUTIONS=0

EA4E33A_INITIAL_REQUALIFICATION_RESULT=HOLD
EA4E33A_PROCESS_PROBE_INCIDENT=YES
EA4E33A_OPENCODE_VERSION_PROBES=8
```

Existing EA-4E.33A output and evidence prove that the processes only executed
the receiver's `--version` path or the equivalent metadata helper. No task,
prompt, adapter `execute`, production boundary, or model invocation was
entered.

## Root Cause

```text
INCIDENT_PROBE_COUNT_CONFIRMED=8
INCIDENT_PROBE_COMMAND=<qualified-opencode-executable> --version
INCIDENT_PROBE_SOURCE_FILES=tests/hermes_core/test_opencode_adapter.py;tools/hermes_core/opencode_adapter.py
INCIDENT_PROBE_SOURCE_SYMBOLS=resolve_pinned_binary;qualify_opencode_runtime;OpenCodeReceiverAdapter.qualify_runtime;OpenCodeLiveProcess.start;_version_probe
INCIDENT_PROBE_TRIGGER_PHASE=TEST_BODY
INCIDENT_ROOT_CAUSE_CLASSIFICATION=IDENTITY_DISCOVERY,CAPABILITY_DISCOVERY,TEST_HELPER_PROBE
```

The exact triggering tests were:

1. `TestOpenCodeBinaryVerification::test_real_binary_matches_pin`
2. `TestOpenCodeArgv::test_build_argv_matches_qualified_transport`
3. `TestOpenCodeArgv::test_build_argv_rejects_unsafe_run_id`
4. `TestOpenCodeReceiverAdapter::test_qualify_runtime`
5. `TestOpenCodeReceiverAdapter::test_build_argv`
6. `TestOpenCodeReceiverAdapter::test_prepare_invocation`
7. `TestOpenCodeLiveProcess::test_version_probe_from_safe_cwd`
8. `TestOpenCodeNonInferenceControl::test_opencapture_version_pipe_capture`

Seven tests reached `_version_probe()` through binary identity or capability
qualification. The eighth used `OpenCodeLiveProcess.start()` as a test helper.
No probe occurred during module import, test collection, a constructor, or a
fixture.

```text
INCIDENT_RECEIVER_TASKS=0
INCIDENT_MODEL_INVOCATIONS=0
INCIDENT_ADAPTER_EXECUTIONS=0
INCIDENT_PRODUCTION_BOUNDARY_EXECUTIONS=0
```

## Process-Boundary Remediation

The eight tests now use test-owned executable bytes, a computed test digest,
an injected deterministic version probe, fake runtime bindings, or
`OpenCodeFakeProcess`. Production OpenCode metadata and execution behavior was
not changed.

An environment-gated collection/session guard in
`tests/hermes_core/conftest.py` intercepts `subprocess.Popen`,
`subprocess.run`, `asyncio.create_subprocess_exec`, and
`asyncio.create_subprocess_shell`. Its sole process allowlist entry is the
exact current Python executable followed by the exact test helper path and a
`claim` or `precommit-crash` mode. There are no receiver-binary allowlist
entries.

```text
NONLIVE_OPENCODE_VERSION_PROBE_ENABLED=NO
NONLIVE_KILO_VERSION_PROBE_ENABLED=NO
NONLIVE_BINARY_CAPABILITY_DISCOVERY_USES_FAKE=YES
GENERIC_SUBPROCESS_TRIPWIRE_PRESENT=YES
RECEIVER_BINARY_PROCESS_TRIPWIRE_PRESENT=YES
HELPER_PROCESS_ALLOWLIST_EXPLICIT=YES
RECEIVER_BINARY_ALLOWLIST_ENTRIES=0
OPENCODE_BINARY_START_ATTEMPTS_ALLOWED=NO
KILO_BINARY_START_ATTEMPTS_ALLOWED=NO
CODEX_BINARY_START_ATTEMPTS_ALLOWED=NO
PROCESS_PROBES_CAN_OCCUR_DURING_COLLECTION=NO
COLLECTION_PHASE_RECEIVER_PROCESS_BLOCKED=YES
PRODUCTION_RECEIVER_METADATA_BEHAVIOR_CHANGED=NO
PRODUCTION_EXECUTION_SEMANTICS_CHANGED=NO
PRODUCTION_AUTHORIZATION_SEMANTICS_CHANGED=NO
```

The SQLite concurrency helper was corrected during the final regression loop.
The test already allowed an `ERROR` race outcome, but the helper previously
exited without printing that token when an operational exception occurred.
It now reports `ERROR` deterministically while the test continues to require
exactly one `ALLOW` and exactly one durable consumption. No production code or
assertion was weakened.

## Test Classification

All 113 `tests/hermes_core/test_*.py` candidate suites were classified before
the strict run. The 100 files outside the exclusion set below have
`IMPORT_CAN_LAUNCH_RECEIVER_PROCESS=NO`,
`FIXTURE_CAN_LAUNCH_RECEIVER_PROCESS=NO`,
`TEST_BODY_CAN_LAUNCH_RECEIVER_PROCESS=NO`, and
`SAFE_FOR_STRICT_NONLIVE=YES`. This classification was enforced at collection
and execution by the generic process tripwire rather than inferred only from
filenames.

The following 13 files were classified
`SAFE_FOR_STRICT_NONLIVE=NO` and excluded:

| Suite | Import | Fixture | Body | Reason |
| --- | --- | --- | --- | --- |
| `test_codex_adapter.py` | No | No | Yes | Environment-bound receiver metadata |
| `test_codex_schema_contract.py` | No | No | No | Environment dependency absent |
| `test_kilo_adapter.py` | No | No | Yes | Environment-bound receiver metadata |
| `test_opencode_adapter.py` | No | No | Yes | File contains separately governed live-capable tests; eight remediated tests ran separately |
| `test_opencode_adapter_parser.py` | No | No | Yes | Environment-bound captured receiver data |
| `test_production_activation.py` | No | No | Yes | Activation boundary |
| `test_kilo_invocation_authorized_live.py` | No | No | Yes | Explicit live invocation |
| `test_opencode_invocation_authorized_live.py` | No | No | Yes | Explicit live invocation |
| `test_opencode_invocation_authorized_live_25a.py` | No | No | Yes | Explicit live invocation |
| `test_opencode_invocation_authorized_live_25ra.py` | No | No | Yes | Explicit live invocation |
| `test_opencode_invocation_authorized_live_25rb.py` | No | No | Yes | Explicit live invocation |
| `test_execution_launch_coordinator_real_probe.py` | No | No | Yes | Generic real-process probe |
| `test_local_worker_runtime_adapter_process.py` | No | No | Yes | Generic worker-process execution |

```text
STRICT_NONLIVE_SUITES_CLASSIFIED=113
STRICT_NONLIVE_SUITES_EXCLUDED=13
ACTIVATION_TESTS_CLASSIFIED_SAFE_FOR_NONLIVE=NO
ACTIVATION_TESTS_EXECUTED_AS_NONLIVE=NO
```

## Requalification Tests

```text
INCIDENT_SOURCE_TESTS=8
INCIDENT_SOURCE_TEST_FAILURES=0
NEW_OPENCODE_VERSION_PROBES=0
NEW_RECEIVER_BINARY_PROCESSES=0

EA4E33A_DEDICATED_TESTS=33
EA4E33A_DEDICATED_FAILURES=0

EA4E33_DEDICATED_TESTS=91
EA4E33_DEDICATED_FAILURES=0

EA4E32_DEDICATED_TESTS=52
EA4E32_DEDICATED_FAILURES=0

COMBINED_AUTH_RUNTIME_TESTS=383
COMBINED_AUTH_RUNTIME_FAILURES=0

FINAL_STRICT_NONLIVE_TEST_TOTAL=2021
FINAL_STRICT_NONLIVE_SUBTEST_TOTAL=104
FINAL_STRICT_NONLIVE_FAILURES=0
```

The combined set has two more tests than the historical 381-test floor. The
final strict set is smaller than the historical 2,039-test safe set because
the process reclassification additionally excludes the real-probe and local
worker-process suites.

Two broad attempts produced isolated concurrency-fixture failures. First, a
SQLite helper emitted empty stdout where the fixture contract permitted the
explicit `ERROR` token; the narrow helper correction above resolved it and the
33-test dedicated suite passed. Second, a legacy thread-concurrency test
returned `error` rather than `conflict` during a broad run; it passed
immediately in isolation without modification. The mandatory complete rerun
then passed 2,021 tests and 104 subtests with zero failures.

## Process Accounting

The append-only strict-process audit contains 72 entries across all focused,
combined, failed, isolated, and final reruns. Every entry is an exact
allowlisted SQLite test-helper start. Repetition accounts for the total.

```text
NEW_OPENCODE_BINARY_PROCESSES=0
NEW_KILO_BINARY_PROCESSES=0
NEW_CODEX_BINARY_PROCESSES=0
NEW_RECEIVER_PROCESSES=0
NEW_MODEL_INVOCATIONS=0
SQLITE_HELPER_PROCESSES=72

NEW_KILO_TASKS=0
NEW_OPENCODE_TASKS=0
REAL_KILO_EXECUTOR_INSTANTIATIONS=0
REAL_OPENCODE_EXECUTOR_INSTANTIATIONS=0
REAL_KILO_EXECUTOR_CALLS=0
REAL_OPENCODE_EXECUTOR_CALLS=0
REAL_KILO_ADAPTER_CALLS=0
REAL_OPENCODE_ADAPTER_CALLS=0
LIVE_BINDINGS_CREATED=0
LIVE_INVOCATION_AUTHS_ISSUED=0
LIVE_DISPATCH_EXECUTIONS=0
PRODUCTION_BOUNDARY_REAL_EXECUTIONS=0
PRODUCTION_AUTH_STORE_TOUCHED=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

## Tripwires

```text
REAL_EXECUTOR_TRIPWIRE_HITS=0
REAL_ADAPTER_TRIPWIRE_HITS=0
PROCESS_START_TRIPWIRE_HITS=0
RECEIVER_BINARY_TRIPWIRE_HITS=0
PROCESS_AUDIT_BLOCKED_RECORDS=0
PROCESS_AUDIT_RECEIVER_RECORDS=0
```

## EA-4E.33A Architecture

```text
STORE_INSTANCE_ID_PRESENT=YES
EXPECTED_STORE_IDENTITY_STORED_OUTSIDE_PRIMARY_DB=YES
STORE_GENERATION_PRESENT=YES
EXPECTED_GENERATION_STORED_OUTSIDE_PRIMARY_DB=YES
STALE_BACKUP_REPLAY_ATTEMPT=DENY
STALE_BACKUP_ROLLBACK_DETECTED=YES
UNEXPECTED_VALID_DB_REPLACEMENT_DETECTED=YES
AUTHORIZATION_STATE_FROM_REPLACEMENT_ACCEPTED=NO
AMBIGUOUS_DB_ANCHOR_STATE_FAILS_CLOSED=YES
```

## Clock Semantics

```text
EA4E23_EXPIRY_SEMANTIC_INTERPRETATION=A_CURRENT_TRUSTED_UTC_WALL_CLOCK
CLOCK_ROLLBACK_REVALIDATION_REPRODUCED=YES
CLOCK_TRUST_IS_EXTERNAL_ASSUMPTION=YES
OBSERVED_EXPIRED_STATE_PERSISTED=NO
CLOCK_ROLLBACK_AFTER_EXPIRY=ALLOW_IF_CURRENT_TRUSTED_CLOCK_IS_AGAIN_BEFORE_EXPIRY_AND_AUTH_IS_UNCONSUMED
```

No sealed expiry semantic was changed.

## Contracts

```text
EA4E23=e638e8ff695172eceaf5c36baa1f5063633b32e344971a7d6fc54cf456faff91
EA4E26=84aad8495a6ec034c763f8c62a98ec41e85ef48c2b453bd098bc3cf57f624a67
EA4E28=395944480c5ea2cde374b07093f07b6e44633f404abb8e420136ee5516b910e1
EA4E29=821941da6ea4b08105c359afeb86193e343a429b0a74a32826bd6370faaa5166
SEALED_CONTRACT_CHAIN_UNCHANGED=YES
EA4E23_CONTRACT_CHANGE_REQUIRED=NO
EA4E26_CONTRACT_CHANGE_REQUIRED=NO
EA4E28_CONTRACT_CHANGE_REQUIRED=NO
EA4E29_CONTRACT_CHANGE_REQUIRED=NO
SEALED_CONTRACT_DEFECT_FOUND=NO
```

## Repository

```text
UNRELATED_WIP_TOUCHED=NO
STAGED=0
COMMIT=NO
PUSH=NO
EA4E33B_EVIDENCE_CREATED=YES
```

## Final Disposition

```text
EA-4E.33B =
PASS /
8-OPENCODE-METADATA-PROBE INCIDENT FULLY ACCOUNTED /
STRICT NON-LIVE PROCESS BOUNDARY RESTORED /
RECEIVER BINARY METADATA DISCOVERY FULLY FAKED IN QUALIFICATION /
NO OPENCODE KILO OR CODEX BINARY PROCESS STARTS /
EA-4E.33A DURABLE STORE ROLLBACK-DETECTION REMEDIATION REQUALIFIED /
EA-4E.33 AND EA-4E.32 REMAIN QUALIFIED /
SEALED CONTRACT CHAIN UNCHANGED /
STRICT SAFE NON-LIVE REGRESSION CLEAN /
NO REAL RECEIVER MODEL ADAPTER OR PRODUCTION EXECUTION /
NOT COMMITTED

EA-4E.33A =
QUALIFIED NON-LIVE AFTER EA-4E.33B PROCESS-BOUNDARY REQUALIFICATION

NEXT_PHASE=EA-4E.30-33B CONSOLIDATED LOCAL COMMIT REVIEW AND REMOTE CHECKPOINT
```

No live receiver execution or receiver-binary metadata probing is authorized
by this result.
