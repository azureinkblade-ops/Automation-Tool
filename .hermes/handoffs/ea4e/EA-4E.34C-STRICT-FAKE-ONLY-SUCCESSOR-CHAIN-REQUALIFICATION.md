# EA-4E.34C Strict Fake-Only Successor-Chain Requalification

## Disposition

```text
EA-4E.34C=PASS
EA-4E.34B=QUALIFIED_NONLIVE_AFTER_EA4E34C_PROCESS_BOUNDARY_REQUALIFICATION
COMMIT=NO
PUSH=NO
LIVE_AUTHORIZATION=NO
```

EA-4E.34, EA-4E.34A, and the original EA-4E.34B run remain historical HOLD
records. EA-4E.34C qualifies the uncommitted successor-chain implementation;
it does not rewrite those outcomes.

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

## EA-4E.34B Incident Forensics

```text
EA4E34B_PRIOR_RESULT=HOLD
EA4E34B_PRIOR_BLOCKED_PROCESS_ATTEMPTS=5
EA4E34B_PRIOR_RECEIVER_PROCESSES_STARTED=0
EA4E34B_PRIOR_MODEL_INVOCATIONS=0
BLOCKED_PROCESS_ATTEMPT_COUNT_CONFIRMED=5
```

| Test | Source symbol | Command | Classification | Final qualification |
|---|---|---|---|---|
| `test_execute_success` | `TestKiloFakeProcess.test_execute_success` | `echo hello` | PROCESS_CONTROLLER_UNIT_TEST | Excluded |
| `test_execute_failure_exit_code` | `TestKiloFakeProcess.test_execute_failure_exit_code` | `cmd /c exit 1` | PROCESS_CONTROLLER_UNIT_TEST | Excluded |
| `test_execute_timeout_reported_via_fake_process` | `TestKiloFakeProcess.test_execute_timeout_reported_via_fake_process` | `echo hello` | PROCESS_CONTROLLER_UNIT_TEST | Excluded |
| `test_version_probe_from_safe_cwd` | `TestKiloLiveProcess.test_version_probe_from_safe_cwd` | `kilo.exe --version` | METADATA_PROBE | Excluded |
| `test_stdin_is_closed_not_a_task_channel` | `TestKiloStdinClosure.test_stdin_is_closed_not_a_task_channel` | `echo hello` | PROCESS_CONTROLLER_UNIT_TEST | Excluded |

All are in `tests/hermes_core/test_kilo_adapter.py`. Process creation is the
behavior under test in four cases. The fifth metadata test intentionally runs
the real executable. None is safe for a zero-process qualification, and none
was executed in the final run.

```text
NONLIVE_KILO_VERSION_PROBE_ENABLED=NO
KILO_METADATA_IN_STRICT_NONLIVE_USES_FAKE=YES
PROCESS_CONTROLLER_TESTS_CLASSIFIED_SAFE_FOR_STRICT_FAKE_ONLY=NO
PROCESS_CONTROLLER_TESTS_EXECUTED_IN_FINAL_QUALIFICATION=NO
PRODUCTION_KILO_METADATA_BEHAVIOR_CHANGED=NO
PRODUCTION_KILO_ADAPTER_BEHAVIOR_CHANGED=NO
PRODUCTION_KILO_EXECUTOR_BEHAVIOR_CHANGED=NO
```

The strict suite consumes frozen metadata constants and canonical material.
The executable itself was identified outside pytest by file size and SHA-256;
it was never started.

## Successor Identity

```text
KILO_SUCCESSOR_VERSION=7.5.15
KILO_SUCCESSOR_SIZE=170690048
KILO_SUCCESSOR_SHA256=78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25
NEW_KILO_TRANSPORT_CONTRACT_ID=d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd
TRANSPORT_ID_RECOMPUTED=YES
TRANSPORT_ID_MATCHES_PROVISIONAL=YES
NEW_KILO_EXECUTABLE_BINDING_ID=01274cc23910aebfbbd4666fffea5ce560d80720160a6909e2157576ad177982
EXECUTABLE_BINDING_ID_RECOMPUTED=YES
EXECUTABLE_BINDING_ID_MATCHES_PROVISIONAL=YES
KILO_MODEL_BINDING_CHANGED=NO
```

Repeated calls, fresh imports/builders, reversed mapping order, irrelevant
task text, and changed-dependency tests all passed. The installed VSIX does not
publish a source commit, so the canonical transport truthfully records
`UNAVAILABLE_IN_INSTALLED_VSIX_METADATA` instead of retaining stale 7.5.6
provenance.

## Dependency Roll

The graph was recomputed from canonical payload builders and is acyclic:

```text
Kilo transport -> EA-4E.6 -> EA-4E.7 -> EA-4E.8/11
EA-4E.6/7/11 -> EA-4E.14 -> EA-4E.17 -> EA-4E.18
EA-4E.17/18 + receiver binding -> EA-4E.21 -> EA-4E.22
EA-4E.14/17/18/21/22 -> EA-4E.23 -> EA-4E.26 -> EA-4E.28 -> EA-4E.29
```

```text
CONTRACT_DEPENDENCY_GRAPH_RECOMPUTED=YES
CONTRACT_DEPENDENCY_GRAPH_ACYCLIC=YES
ALL_EA4E6_TO_29_ARTIFACTS_REVIEWED=YES
ROLLED_ARTIFACT_COUNT=13
ROLLED_ARTIFACTS=EA-4E.6,EA-4E.7,EA-4E.8,EA-4E.11,EA-4E.14,EA-4E.17,EA-4E.18,EA-4E.21,EA-4E.22,EA-4E.23,EA-4E.26,EA-4E.28,EA-4E.29
UNCHANGED_ARTIFACT_COUNT=11
UNCHANGED_ARTIFACTS=EA-4E.9,EA-4E.10,EA-4E.12,EA-4E.13,EA-4E.15,EA-4E.16,EA-4E.19,EA-4E.20,EA-4E.24,EA-4E.25,EA-4E.27
ROLL_SET_CHANGED_DURING_34C=NO
EA4E30_TO_33B_ROLL_REQUIRED=NO
AUTH_STORE_SCHEMA_CHANGE_REQUIRED=NO
AUTH_STORE_ANCHOR_SCHEMA_CHANGE_REQUIRED=NO
```

The unchanged entries are qualification/evidence phases without a current
sealed builder dependent on the Kilo transport. EA-4E.30 through 33B retain
their durability semantics; only current-chain test fixtures were rebound.

## Rolled IDs

| Artifact | Successor ID |
|---|---|
| EA-4E.6 | `292f7deeb479cd45c6f33f3466305e7f225c05d9f48f9eeb8dc13f944d7162a1` |
| EA-4E.7 | `6de9f8b959db33bd2c2885396507baed47a3eadf07423c0e545afe4cc3274661` |
| EA-4E.8 | `9785647334992c514ef56013c2e410be48c42a3c1813b377e601823387be67a2` |
| EA-4E.11 | `af7d731ff21614f3ab0e92beb8927d3063e06707af7a9a89bc3d3b7c91e7927a` |
| EA-4E.14 | `b057272ee70a4f5fceb9500ccf699097ed2de2edfc21e8f47fe3f9247e52f20b` |
| EA-4E.17 | `5082b1a227a53cfe711bcf3c5d2193cd47031d75d7ec7650d8ab4c2389194e93` |
| EA-4E.18 | `56471e6509ccc2e99a7b609354748c51a0ada18bda8b92648c21bec584c1ceb3` |
| EA-4E.21 | `a25a6ba03b6a44f35511bec4b89c332043cd252ea3d1e185bd1b0a5c966fee33` |
| EA-4E.22 | `0e9d206a0b5d78592bafad624421439774e6c7ffe34a7c9d4c41a66aeb0504bd` |
| EA-4E.23 | `7bc3d2e036beacaef5aaabd054730dfbd49c57a0c36bbaab6f56894798be4687` |
| EA-4E.26 | `2e7a4b360c54541ff408e8430d3ac9a28cdee76e0feef5e1da03b87a889657ba` |
| EA-4E.28 | `90c96695f6294bed90eed1b630b1b44f7faca859b6b818ea2a744c1b753eb5b1` |
| EA-4E.29 | `00c6808dada4c9cf74a0310a31c9a51b10c1a8ee770f8f6c8a45d4d1f4962dd2` |

## Fake Qualification

The focused successor test contains the ten specifically required mismatch
combinations plus ten additional binding-policy mismatches. All reject.

```text
SUCCESSOR_FAKE_POSITIVE_PATH=PASS
SUCCESSOR_MISMATCH_CASES=20
SUCCESSOR_MISMATCH_UNSAFE_ALLOWS=0
ROUTE_SELECTED=YES
AUTHORITY_VALID=YES
ACTIVATION_VALID=YES
EXECUTOR_BINDING_VALID=YES
INVOCATION_AUTHORIZATION_VALID=YES
ATOMIC_CLAIM=ALLOW
FAKE_EXECUTOR_CALLED_ONCE=YES
REAL_EXECUTOR_CALLED=NO
```

## Durability And Rollback

```text
NEW_CHAIN_AUTH_ISSUANCE_DURABLE=YES
NEW_CHAIN_AUTH_CONSUMPTION_DURABLE=YES
NEW_CHAIN_POST_RESTART_REPLAY_DENIED=YES
NEW_CHAIN_CROSS_RECEIVER_REPLAY_DENIED=YES
NEW_CHAIN_STALE_BACKUP_REPLAY_DENIED=YES
NEW_CHAIN_VALID_DB_REPLACEMENT_DETECTED=YES
NEW_CHAIN_DB_ANCHOR_MISMATCH_FAILS_CLOSED=YES
STORE_IDENTITY_SEMANTICS_CHANGED=NO
STORE_GENERATION_SEMANTICS_CHANGED=NO
ROLLBACK_DETECTION_SEMANTICS_CHANGED=NO
```

## Final Safe Suite Manifest

Twenty files were selected by reachability:

```text
FINAL_SAFE_SUITE_COUNT=20
FINAL_SAFE_SUITE_MANIFEST=test_ea4e34b_kilo_successor_contract_roll.py,test_receiver_router.py,test_receiver_dispatch.py,test_production_dispatch.py,test_production_activation.py,test_production_execution.py,test_production_issuance.py,test_governed_production.py,test_production_executor_binding.py,test_governed_bound_executor.py,test_production_invocation_authorization.py,test_governed_production_runtime.py,test_production_invocation_authorization_issuer.py,test_governed_production_caller.py,test_ea4e31_restart_durability_contracts.py,test_ea4e32_restart_durable_authorization.py,test_ea4e33_operational_safety.py,test_ea4e33a_store_rollback_detection.py,test_governed_production_runtime_26b.py,test_governed_production_runtime_27.py
```

Fourteen mixed, process-oriented, or live-capable suites were excluded:

```text
FINAL_EXCLUDED_SUITE_COUNT=14
FINAL_EXCLUDED_SUITE_MANIFEST=
test_kilo_adapter.py:MIXED_PROCESS_CREATION_REQUIRED_AND_METADATA_REAL_BINARY_PROBE
test_kilo_live_binding.py:ACTIVATION_PATH
test_kilo_invocation_authorized_live.py:LIVE_BINARY_REQUIRED
test_production_kilo_qualification.py:REAL_ADAPTER_TEST
test_kilo_fully_governed.py:REAL_EXECUTOR_TEST
test_opencode_adapter.py:OTHER_MIXED_TRANSPORT_PROCESS_SUITE
test_opencode_live_binding.py:ACTIVATION_PATH
test_opencode_invocation_authorized_live.py:LIVE_BINARY_REQUIRED
test_opencode_invocation_authorized_live_25a.py:LIVE_BINARY_REQUIRED
test_opencode_invocation_authorized_live_25ra.py:LIVE_BINARY_REQUIRED
test_opencode_invocation_authorized_live_25rb.py:LIVE_BINARY_REQUIRED
test_opencode_fully_governed.py:REAL_EXECUTOR_TEST
test_codex_live_process.py:LIVE_BINARY_REQUIRED
test_local_worker_runtime_adapter_process.py:PROCESS_CREATION_REQUIRED
```

No import or collection attempt reached a process. The exact SQLite helper is
the only process allowlist entry used by the final suite.

## Test Results

```text
EA4E21_KILO_SAFE_TESTS=110
EA4E21_KILO_SAFE_FAILURES=0
EA4E22_KILO_SAFE_TESTS=67
EA4E22_KILO_SAFE_FAILURES=0
EA4E23_KILO_SAFE_TESTS=38
EA4E23_KILO_SAFE_FAILURES=0
EA4E26_KILO_SAFE_TESTS=64
EA4E26_KILO_SAFE_FAILURES=0
EA4E28_KILO_SAFE_TESTS=27
EA4E28_KILO_SAFE_FAILURES=0
EA4E29_KILO_SAFE_TESTS=11
EA4E29_KILO_SAFE_FAILURES=0
EA4E33B_PROCESS_GUARD_SAFE_TESTS=91
EA4E33B_PROCESS_GUARD_SAFE_FAILURES=0
GUARD_UNIT_TESTS_RUN_SEPARATELY=YES
GUARD_UNIT_TEST_BLOCKED_ATTEMPTS=5
FINAL_QUALIFICATION_COUNTERS_RESET_AFTER_GUARD_UNIT_TESTS=YES
FINAL_STRICT_FAKEONLY_TEST_TOTAL=751
FINAL_STRICT_FAKEONLY_SUBTEST_TOTAL=0
FINAL_STRICT_FAKEONLY_FAILURES=0
TESTS_SKIPPED_FOR_PASSING_PURPOSES=0
TESTS_XFAILED_FOR_PASSING_PURPOSES=0
ASSERTIONS_WEAKENED=NO
REASON_CODES_LOOSENED=NO
FORCED_TEST_ORDERING=NO
```

The five guard-unit blocked attempts are the historical EA-4E.34B incident.
EA-4E.34C did not repeat them; its final counter was a new empty audit file.

## Final Process Accounting

```text
STRICT_PROCESS_GUARD_ACTIVE=YES
GENERIC_PROCESS_CREATION_BLOCKED=YES
SQLITE_HELPER_ALLOWLIST_EXPLICIT=YES
RECEIVER_BINARY_ALLOWLIST_ENTRIES=0
PROCESS_CONTROLLER_TEST_ALLOWLIST_ENTRIES=0
COLLECTION_PHASE_PROCESS_ATTEMPTS=0
IMPORT_TIME_PROCESS_ATTEMPTS=0
KILO_BINARY_PROCESSES=0
OPENCODE_BINARY_PROCESSES=0
CODEX_BINARY_PROCESSES=0
RECEIVER_PROCESSES=0
MODEL_INVOCATIONS=0
BLOCKED_PROCESS_ATTEMPTS=0
SQLITE_HELPER_PROCESSES=9
REAL_KILO_EXECUTOR_CALLS=0
REAL_OPENCODE_EXECUTOR_CALLS=0
REAL_KILO_ADAPTER_CALLS=0
REAL_OPENCODE_ADAPTER_CALLS=0
LIVE_BINDINGS_CREATED=0
LIVE_INVOCATION_AUTHS_ISSUED=0
LIVE_DISPATCH_EXECUTIONS=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

## Governance

```text
OLD_KILO_7_5_9_TRANSPORT_ID_PRESERVED=YES
OLD_DOWNSTREAM_CONTRACT_IDS_PRESERVED=YES
HISTORICAL_REFERENCES_NOT_MUTATED_IN_PLACE=YES
OPENCODE_TRANSPORT_ID_UNCHANGED=YES
OPENCODE_MODEL_BINDING_ID_UNCHANGED=YES
OPENCODE_UNRELATED_CONTRACT_CHANGES=0
QUALIFIED_RECEIVER_SET_CHANGED=NO
PRODUCTION_KILO_BINDING_ACTIVATED=NO
LIVE_KILO_ENABLED=NO
LIVE_OPENCODE_ENABLED_BY_THIS_PHASE=NO
AUTOMATIC_KILO_VERSION_SELECTION=NO
AUTOMATIC_EXECUTABLE_FALLBACK=NO
UNRELATED_WIP_TOUCHED=NO
STAGED=0
COMMIT=NO
PUSH=NO
```

## Next Boundary

```text
NEXT_PHASE=EA-4E.34B/34C SUCCESSOR-CHAIN LOCAL COMMIT REVIEW AND REMOTE CHECKPOINT
```

No live Kilo, OpenCode, Codex, receiver, model, GPU, or ComfyUI execution was
authorized or performed.
