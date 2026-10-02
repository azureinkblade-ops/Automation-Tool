# EA-4E.34E Bad Continuation Containment

## Purpose

Contain and reverse only unauthorized worktree mutations from the failed
EA-4E.34 continuation that drifted into an obsolete EA-4E.32 workflow.

This phase is containment, not remediation, not live qualification, and not
an EA-4E.32 restart.

## Governing State

```text
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=64b6c1e522394713b8ec22500273aabcadd289c2
GOVERNING_REMOTE_HEAD=64b6c1e522394713b8ec22500273aabcadd289c2
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
INITIAL_STAGED=0
```

Committed baseline matched the sealed successor-chain checkpoint. Restoration
was performed against this checkpoint only.

## Bad Continuation Summary

A later session treated an interrupted EA-4E.32 authorization as the active
task, then mutated files outside EA-4E.34 live-qualification authorization.

Observed unauthorized acts:

- rewrote historical contract-ID expectations in two live-path test files
- created a new EA-4E.32 evidence file
- ran broad pytest (not part of this containment)
- deleted gitignored `automation_state.db` (cannot reconstruct)

No Kilo, OpenCode, Codex, or model process was started by that continuation.
No live invocation authorization was issued. No commit or push occurred.

```text
EA4E32_PRIOR_SESSION_INTERRUPTED_BY_USAGE_LIMIT=YES
EA4E32_INTERRUPTION_WAS_NOT_GOVERNANCE_FAILURE=YES
BAD_CONTINUATION_REENTERED_EA4E32=YES
```

## Pre-Bad-Run Reconstruction

```text
PRE_BAD_RUN_STATE_RECONSTRUCTED=YES
```

Sources:

- sealed commit `64b6c1e522394713b8ec22500273aabcadd289c2`
- worktree snapshot taken at that HEAD immediately before the unauthorized
  test-file patches (three tracked modifications, remaining files untracked)
- git blob hashes after restoration

Pre-bad-run tracked modifications at `64b6c1e`:

- `.hermes/handoffs/ea4e/EA-4E.6-RECEIVER-ROUTER-FAKE-QUALIFICATION.md`
- `tools/hermes_core/__init__.py`
- `tools/hermes_core/receiver_registry.py`

Those three files were already modified before the bad continuation. They were
not patched by it. They were left untouched.

## Start WIP Inventory

```text
ALL_CURRENT_WIP_FILE_COUNT=45
STAGED=0
DELETED_TRACKED=0
```

## Classification

### UNAUTHORIZED_BAD_CONTINUATION_FILES

```text
tests/hermes_core/test_kilo_invocation_authorized_live.py
tests/hermes_core/test_opencode_invocation_authorized_live_25ra.py
.hermes/handoffs/ea4e/EA-4E.32-RESTART-DURABLE-AUTHORIZATION-IMPLEMENTATION.md
```

### PREEXISTING_EA4E_WIP_FILES

```text
.hermes/handoffs/ea4e/EA-4E.6-RECEIVER-ROUTER-FAKE-QUALIFICATION.md
.hermes/handoffs/ea4e/EA-4E.3R-KILO-TRANSPORT-REVISION-FOR-TRUSTED-MODEL-BINDING.md
.hermes/handoffs/ea4e/EA-4E.3R3-KILO-FIXED-FREE-MODEL-REBIND.md
.hermes/handoffs/ea4e/EA-4E.4-OPENCODE-OUTPUT-CAPTURE-DIAGNOSTIC.md
.hermes/handoffs/ea4e/EA-4E.4-OPENCODE-OUTPUT-CAPTURE-REMEDIATION.md
.hermes/handoffs/ea4e/EA-4E.5-KILO-ONE-SHOT-LIVE-QUALIFICATION-RESULT.md
tools/hermes_core/__init__.py
tools/hermes_core/receiver_registry.py
tools/hermes_core/kilo_fully_governed.py
.pytest-ea4e34d-checkpoint-audit.jsonl
.pytest_iso/test_version_probe_from_safe_c0/spool/run-16e624c4.stderr.txt
.pytest_iso/test_version_probe_from_safe_c0/spool/run-16e624c4.stdout.jsonl
```

### PREEXISTING_UNRELATED_WIP_FILES

```text
.hermes/handoffs/ea4d4f/EA-4D.4F-R10-LIVE-GPU-PILOT-RESULT.md
.hermes/handoffs/ea4d4f/EA-4D.4F-R9-LIVE-PILOT-AUTHORIZATION-PACKET.md
.hermes/handoffs/ea4d4f/R8-HOLD-RESOLUTION-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-01-source-freeze-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-02-canonical-input-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-03-repair-identity-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-04-comfyui-boundary-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-05-submission-semantics-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-06-pixel-immutability-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-07-verification-layers-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-08-failure-ownership-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-09-cleanup-ownership-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-10-pilot-root-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-11-authority-integration-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-12-activation-separation-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-13-recovery-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-14-source-freeze-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-15-verification-ladder-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-17-source-closure-FROZEN.md
.hermes/handoffs/ea4d4f/STEP-18-composition-boundary-FROZEN.md
.hermes/handoffs/ea4d4f/STEP-19-source-freeze-READY.md
.hermes/handoffs/ea4d4f/STEP-20-R8-source-closure-review-COMPLETE.md
.hermes/handoffs/ea4d4f/STEP-21-live-pilot-identity-freeze.md
.hermes/handoffs/ea4d4f/STEP-22-live-gpu-pilot-COMPLETE.md
.hermes/handoffs/ea4d4f/source-freeze-manifest.json
EA-4D.4F-R6-CANONICAL_PILOT_CONTRACT.md
EA-4D.4F-R6-DESIGN_HANDOFF.md
temp_update.md
tools/image_pipeline_v2_execution.py
tools/image_pipeline_v2_provenance.py
```

### GENERATED_TEMP_FILES

Permission-denied `.pytest-*` directories already present before the bad
continuation. Not restored. Not deleted.

Gitignored `automation_state.db` was deleted by the bad continuation
(`rm -f automation_state.db`). It is ignored by `.gitignore:34`. Contents
cannot be reconstructed. It is not a git-tracked WIP file.

### AMBIGUOUS_FILES

```text
AMBIGUOUS_FILES=
```

## Reported File Review

### tests/hermes_core/test_kilo_invocation_authorized_live.py

```text
FILE=tests/hermes_core/test_kilo_invocation_authorized_live.py
STATE_AT_64B6C1E=tracked committed blob db7f2671087f8d47d1785e406da9378b989f8803
STATE_BEFORE_BAD_RUN=identical to HEAD (not in porcelain)
STATE_AFTER_BAD_RUN=4 contract-ID expectation substitutions
CLASSIFICATION=UNAUTHORIZED_BAD_CONTINUATION_CHANGE
RESTORE_ACTION=git restore --source=HEAD -- <file>
```

### tests/hermes_core/test_opencode_invocation_authorized_live_25ra.py

```text
FILE=tests/hermes_core/test_opencode_invocation_authorized_live_25ra.py
STATE_AT_64B6C1E=tracked committed blob 0c91deb92d6b1b3a410d351151b26994bd51fa77
STATE_BEFORE_BAD_RUN=identical to HEAD (not in porcelain)
STATE_AFTER_BAD_RUN=assert replaced with unused EXPECTED assignment
CLASSIFICATION=UNAUTHORIZED_BAD_CONTINUATION_CHANGE
RESTORE_ACTION=git restore --source=HEAD -- <file>
```

### .hermes/handoffs/ea4e/EA-4E.32-RESTART-DURABLE-AUTHORIZATION-IMPLEMENTATION.md

```text
FILE=.hermes/handoffs/ea4e/EA-4E.32-RESTART-DURABLE-AUTHORIZATION-IMPLEMENTATION.md
STATE_AT_64B6C1E=absent
STATE_BEFORE_BAD_RUN=absent
STATE_AFTER_BAD_RUN=untracked file created by bad continuation
CLASSIFICATION=UNAUTHORIZED_BAD_CONTINUATION_CHANGE
RESTORE_ACTION=delete file
EA4E32_EVIDENCE_BAD_RUN_MUTATION_FOUND=YES
EA4E32_EVIDENCE_RESTORED_TO_PRE_BAD_RUN_STATE=YES
```

### tools/hermes_core/__init__.py

```text
FILE=tools/hermes_core/__init__.py
STATE_AT_64B6C1E=tracked without kilo re-exports
STATE_BEFORE_BAD_RUN=already modified (+40 kilo adapter re-exports)
STATE_AFTER_BAD_RUN=unchanged from pre-bad-run
CLASSIFICATION=PREEXISTING_EA4E_WIP
RESTORE_ACTION=none
```

### tools/hermes_core/receiver_registry.py

```text
FILE=tools/hermes_core/receiver_registry.py
STATE_AT_64B6C1E=tracked without _register_kilo_adapter
STATE_BEFORE_BAD_RUN=already modified (+22 explicit kilo registration)
STATE_AFTER_BAD_RUN=unchanged from pre-bad-run
CLASSIFICATION=PREEXISTING_EA4E_WIP
RESTORE_ACTION=none
```

## Restoration Operations

```text
RESTORATION_TARGETS=
  tests/hermes_core/test_kilo_invocation_authorized_live.py
  tests/hermes_core/test_opencode_invocation_authorized_live_25ra.py
  .hermes/handoffs/ea4e/EA-4E.32-RESTART-DURABLE-AUTHORIZATION-IMPLEMENTATION.md

FORBIDDEN_COMMANDS_USED=NO
git restore --source=HEAD -- <two test files>
rm -f <ea4e32 evidence>
git update-index --refresh (stat cache only; no stage)
```

Post-restore blob hashes:

```text
test_kilo_invocation_authorized_live.py = db7f2671087f8d47d1785e406da9378b989f8803 MATCHES_HEAD
test_opencode_invocation_authorized_live_25ra.py = 0c91deb92d6b1b3a410d351151b26994bd51fa77 MATCHES_HEAD
```

```text
TEST_FILES_RESTORED_WITHOUT_ERASING_SUCCESSOR_CHAIN=YES
PRODUCTION_FILES_MATCH_PRE_BAD_RUN_STATE=YES
BAD_RUN_PRODUCTION_FILE_MUTATIONS=
```

Historical test expectations at HEAD were left as the sealed checkpoint stored
them. Containment did not update stale historical assertions.

## Successor Chain

Static import/hash only. No receiver process.

```text
KILO_SUCCESSOR_VERSION=7.5.15
KILO_SUCCESSOR_SHA256=78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25
KILO_TRANSPORT_CONTRACT_ID=d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd
KILO_EXECUTABLE_BINDING_ID=01274cc23910aebfbbd4666fffea5ce560d80720160a6909e2157576ad177982
SUCCESSOR_CHAIN_REVERIFIED=YES
SUCCESSOR_CHAIN_CHANGED_BY_RESTORATION=NO
SEALED_CONTRACT_CHAIN_MATCHES_CHECKPOINT=YES
```

## Unrelated WIP

```text
UNRELATED_WIP_TOUCHED=NO
UNRELATED_WIP_PRESERVED=YES
```

## Tests

```text
BROAD_TEST_SUITE_RUN=NO
```

Only static hash/contract checks were run.

## No Live Activity

```text
KILO_BINARY_PROCESSES=0
OPENCODE_BINARY_PROCESSES=0
CODEX_BINARY_PROCESSES=0
RECEIVER_PROCESSES=0
MODEL_INVOCATIONS=0
LIVE_INVOCATION_AUTHS_ISSUED=0
LIVE_BINDINGS_CREATED=0
LIVE_DISPATCH_EXECUTIONS=0
PRODUCTION_BOUNDARY_REAL_EXECUTIONS=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

## Final Worktree

Git-visible porcelain after restoration, before this evidence file:

42 files, matching the reconstructed pre-bad-run set.

This evidence file is the sole authorized new EA-4E.34E artifact.

```text
FINAL_WORKTREE_MATCHES_PRE_BAD_RUN_STATE=YES
```

Exception: this containment evidence file.

## Repository

```text
STAGED=0
COMMIT=NO
PUSH=NO
```

## Disposition

```text
EA-4E.34E =
PASS /
BAD EA-4E.34 CONTINUATION CONTAINED /
UNAUTHORIZED EA-4E.32 WORKFLOW MUTATIONS IDENTIFIED /
ONLY BAD-CONTINUATION DELTAS RESTORED /
PREEXISTING UNRELATED WIP PRESERVED /
KILO 7.5.15 SUCCESSOR CHAIN REMAINS SEALED /
NO LIVE AUTHORIZATION CONSUMED /
NO RECEIVER OR MODEL EXECUTION /
NOT COMMITTED
```
