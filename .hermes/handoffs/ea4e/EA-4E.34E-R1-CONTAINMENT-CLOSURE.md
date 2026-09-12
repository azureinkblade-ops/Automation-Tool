# EA-4E.34E-R1 Containment Closure

## Purpose

Close two unresolved EA-4E.34E evidence defects:

1. live invocation-authorization accounting
2. `automation_state.db` loss classification

This phase is evidence closure only. No live qualification. No restoration of
unverified database content.

```text
EA4E34E_PRIOR_RESULT=HOLD_PENDING_R1_CLOSURE
EA4E34E_R1_SUBSTANTIVE_CONTAINMENT_FINDINGS_VALID=YES
EA4E34E_TRACKED_BAD_CONTINUATION_DELTAS_RESTORED=YES
EA4E34E_SUCCESSOR_CHAIN_REVERIFIED=YES
EA4E34E_UNRELATED_WIP_PRESERVED=YES
EA4E34E_R1_EVIDENCE_CREATED=YES
EA4E34E_R2_ACCOUNTING_NORMALIZED=YES
```

## Governing State

```text
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=64b6c1e522394713b8ec22500273aabcadd289c2
GOVERNING_REMOTE_HEAD=64b6c1e522394713b8ec22500273aabcadd289c2
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
STAGED_BEFORE=0
```

## Live Authorization Accounting

### Sources of truth (read-only)

```text
LIVE_AUTH_ACCOUNTING_SOURCES=
  1. tools/hermes_core/production_invocation_authorization_issuer.py
     issue() denies DURABLE_INVOCATION_AUTHORIZATION_STORE_REQUIRED when store is None
  2. tools/hermes_core/production_invocation_authorization.py
     evaluate()/claim_for_execution deny the same reason when store is None
  3. tools/hermes_core/durable_invocation_authorization_store.py
     explicit path+anchor required; no default production path; no auto-create on open
  4. tools/hermes_core/runtime_config.py
     execution-authority DB is separate from automation_state.db;
     HERMES_EXECUTION_AUTHORITY_DB default %LOCALAPPDATA%/Hermes/execution_authority.db
     (file does not exist)
  5. sqlite query_only inspection of candidate DBs for table auth_store_metadata
     and invocation_authorizations
  6. bad-continuation command log in this session (pytest only; kilo live tests
     failed with DURABLE_INVOCATION_AUTHORIZATION_STORE_REQUIRED)
  7. .hermes/handoffs/ea4e/EA-4E.34E-BAD-CONTINUATION-CONTAINMENT.md
```

```text
AUTH_STORE_INSPECTION_MODE=READ_ONLY
AUTH_STORE_MUTATED_DURING_R1=NO
```

No production durable invocation-authorization store was found.

Inspected, none contained `auth_store_metadata` or `invocation_authorizations`:

- worktree root: no `automation_state.db` (already deleted)
- main checkout `C:\Users\David\Documents\Automation tool\automation_state.db`
  (tables: post_records, state_snapshots, novels, retrieval_*, release_*, etc.)
- `%LOCALAPPDATA%\Hermes\execution_authority.db` MISSING
- `%LOCALAPPDATA%\Hermes\governance.db` (governance runtime, not EA-4E.23 store)
- `%LOCALAPPDATA%\Hermes\runtime\ea4e\kilo\home\.local\share\kilo\kilo.db`
  (Kilo product session tables)
- `%LOCALAPPDATA%\Hermes\runtime\ea4e\opencode\home\.local\share\opencode\opencode.db`
  (OpenCode product session tables)
- worktree `.hermes/runtime/ea4d4f/**` (EA-4D.4F authority/start/codex-transport)

EA-4E.32 dedicated tests issue into pytest `tmp_path` stores. Those are test
issuances, not live production issuance. They are not counted below.

### Counts for the bad continuation

```text
LIVE_INVOCATION_AUTHS_ISSUED=0
LIVE_INVOCATION_AUTHS_CLAIMED=0
LIVE_INVOCATION_AUTHS_CONSUMED=0
LIVE_EXECUTOR_CALLS=0
LIVE_RECEIVER_EXECUTIONS=0
LIVE_MODEL_INVOCATIONS=0
```

Proof, not inference from "no model output":

- live issue requires an injected `DurableInvocationAuthorizationStore`
- no such production store file exists
- observed kilo live-path pytest failures were DENY /
  `DURABLE_INVOCATION_AUTHORIZATION_STORE_REQUIRED` with `consumed=False`
- no kilo.exe / opencode / Codex receiver process was started in the bad
  continuation or in this R1 session

## automation_state.db

```text
AUTOMATION_STATE_DB_PRIOR_PATH=
  C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot\automation_state.db
AUTOMATION_STATE_DB_GITIGNORED=YES
  source: worktree .gitignore line 34 `/automation_state.db*`
AUTOMATION_STATE_DB_EXISTED_BEFORE_BAD_CONTINUATION=YES
  hermes_core tests have zero references to automation_state;
  the bad continuation only ran hermes_core pytest;
  find listed ./automation_state.db before rm -f
AUTOMATION_STATE_DB_DELETED_BY_BAD_CONTINUATION=YES
  command: rm -f automation_state.db
  in the same worktree cwd
```

The main checkout copy was not deleted:

```text
C:\Users\David\Documents\Automation tool\automation_state.db
exists=YES size=157761536
```

### Ownership / purpose

```text
AUTOMATION_STATE_DB_OWNER_COMPONENT=automation_db.py (Automation Tool monolith)
AUTOMATION_STATE_DB_PURPOSE=
  SQLite source of truth for posts, novels, social stats, retrieval index,
  chapter ledger, release jobs, and related app runtime blobs
  (SCHEMA_VERSION=8, DB_FILENAME=automation_state.db)
AUTOMATION_STATE_DB_CLASSIFICATION=AUTOMATION_TOOL_RUNTIME_STATE
```

Source: `automation_db.py` `DB_FILENAME` and `db_path(root)`.

### EA-4E dependency

```text
AUTOMATION_STATE_DB_USED_BY_EA4E=NO
AUTOMATION_STATE_DB_USED_BY_DURABLE_AUTH_STORE=NO
AUTOMATION_STATE_DB_USED_BY_LIVE_QUALIFICATION=NO
```

Exact references in hermes_core:

- `governance_consumer.py`: consumer "never touches automation_state.db"
- `runtime_config.py`: execution-authority DB "is separate from governance.db
  and automation_state.db"

Durable store schema (`auth_store_metadata`, `invocation_authorizations`) is
absent from the live main `automation_state.db`.

No EA-4E live qualification module constructs
`DurableInvocationAuthorizationStore` against `automation_state.db`.

## Recovery

```text
AUTOMATION_STATE_DB_RECOVERY_SOURCE_FOUND=NO
AUTOMATION_STATE_DB_RECOVERY_SOURCE=NONE
EXACT_PRE_BAD_RUN_COPY_PROVEN=NO
AUTOMATION_STATE_DB_RESTORED=NO
```

Main-repo rotating backups exist under
`C:\Users\David\Documents\Automation tool\migration-backups\rotating\`.
Those are copies of the main checkout DB, not a hashed copy of the deleted
worktree file. Copying them would be a similar DB, not an exact pre-bad-run
worktree copy. Restoration is forbidden.

Worktree `migration-backups/` contains only
`PHASE3_RETIREMENT_BOUNDARY.md` (no DB).

No blank replacement was created.

## Loss Impact

```text
AUTOMATION_STATE_DB_LOSS_AFFECTS_KILO_SUCCESSOR_CHAIN=NO
AUTOMATION_STATE_DB_LOSS_AFFECTS_SEALED_CONTRACT_IDS=NO
AUTOMATION_STATE_DB_LOSS_AFFECTS_DURABLE_REPLAY_STATE=NO
AUTOMATION_STATE_DB_LOSS_CLASSIFICATION=LOSS_NONCRITICAL_BUT_OUTSIDE_EA4E
DB_LOSS_BLOCKS_EA4E34_LIVE_QUALIFICATION=NO
```

Why live qualification is not blocked:

- EA-4E durable replay lives in an explicit-path invocation-authorization store,
  which was never this file
- sealed Kilo 7.5.15 IDs are computed from source/pinned executable identity
- the live Automation Tool DB in the main checkout remains intact
- the lost file was a gitignored worktree-local copy

## Worktree Accuracy

```text
FINAL_WORKTREE_BYTE_FOR_BYTE_MATCHES_PRE_BAD_RUN_STATE=NO
TRACKED_WORKTREE_MATCHES_PRE_BAD_RUN_STATE=YES
EA4E_SUCCESSOR_CHAIN_FILES_MATCH_PRE_BAD_RUN_STATE=YES
UNRELATED_TRACKED_WIP_PRESERVED=YES
```

Byte-for-byte is NO solely because the gitignored worktree
`automation_state.db` remains missing. Tracked files match the reconstructed
pre-bad-run set (plus this R1 evidence file).

## Successor Chain (static)

```text
KILO_SUCCESSOR_VERSION=7.5.15
KILO_SUCCESSOR_SHA256=78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25
KILO_TRANSPORT_CONTRACT_ID=d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd
KILO_EXECUTABLE_BINDING_ID=01274cc23910aebfbbd4666fffea5ce560d80720160a6909e2157576ad177982
SUCCESSOR_CHAIN_REVERIFIED=YES
SEALED_SUCCESSOR_CHAIN_CHANGED=NO
BROAD_TEST_SUITE_RUN=NO
```

## No New Activity (R1)

```text
NEW_LIVE_INVOCATION_AUTHS_ISSUED_DURING_R1=0
NEW_LIVE_INVOCATION_AUTHS_CLAIMED_DURING_R1=0
NEW_LIVE_INVOCATION_AUTHS_CONSUMED_DURING_R1=0
NEW_LIVE_EXECUTOR_CALLS_DURING_R1=0
NEW_LIVE_RECEIVER_EXECUTIONS_DURING_R1=0
NEW_MODEL_INVOCATIONS_DURING_R1=0
KILO_BINARY_PROCESSES=0
OPENCODE_BINARY_PROCESSES=0
CODEX_BINARY_PROCESSES=0
RECEIVER_PROCESSES=0
MODEL_INVOCATIONS=0
```

## Repository

```text
UNRELATED_WIP_TOUCHED=NO
STAGED=0
COMMIT=NO
PUSH=NO
```

## R2 Accounting Normalization

Evidence-only closeout. No new inspection, tests, restoration, or live work.
Mandatory accounting fields are recorded as exact integers, not placeholders.

```text
LIVE_INVOCATION_AUTHS_ISSUED=0
LIVE_INVOCATION_AUTHS_CLAIMED=0
LIVE_INVOCATION_AUTHS_CONSUMED=0
LIVE_EXECUTOR_CALLS=0
LIVE_RECEIVER_EXECUTIONS=0
LIVE_MODEL_INVOCATIONS=0

NEW_LIVE_INVOCATION_AUTHS_ISSUED_DURING_R1=0
NEW_LIVE_INVOCATION_AUTHS_CLAIMED_DURING_R1=0
NEW_LIVE_INVOCATION_AUTHS_CONSUMED_DURING_R1=0
NEW_LIVE_EXECUTOR_CALLS_DURING_R1=0
NEW_LIVE_RECEIVER_EXECUTIONS_DURING_R1=0
NEW_MODEL_INVOCATIONS_DURING_R1=0

AUTH_STORE_INSPECTION_MODE=READ_ONLY
AUTH_STORE_MUTATED_DURING_R1=NO
AUTOMATION_STATE_DB_USED_BY_DURABLE_AUTH_STORE=NO

MANDATORY_ACCOUNTING_PLACEHOLDERS_REMAINING=0
R1_FINAL_DISPOSITION_CONSISTENT_WITH_ACCOUNTING=YES
```

## Final Disposition

```text
EA-4E.34E-R2 =
PASS /
ACCOUNTING PLACEHOLDERS NORMALIZED /
ZERO LIVE AUTHORIZATIONS ISSUED CLAIMED OR CONSUMED DURING BAD CONTINUATION /
ZERO LIVE AUTHORIZATIONS ISSUED CLAIMED OR CONSUMED DURING R1 /
AUTH STORE INSPECTION CONFIRMED READ-ONLY /
AUTOMATION_STATE.DB CONFIRMED OUTSIDE EA-4E DURABLE AUTHORIZATION STATE /
SEALED KILO 7.5.15 SUCCESSOR CHAIN UNCHANGED /
NO NEW TEST PROCESS RESTORATION OR LIVE ACTIVITY /
NOT COMMITTED

EA-4E.34E-R1 =
PASS AFTER R2 ACCOUNTING NORMALIZATION

EA-4E.34E =
PASS

DB_LOSS_BLOCKS_EA4E34_LIVE_QUALIFICATION=NO

NEXT_PHASE=FRESH EA-4E.34 LIVE RESTART-DURABILITY AUTHORIZATION FROM CLEAN CONTEXT
```
