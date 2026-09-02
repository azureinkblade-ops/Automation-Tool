# EA-4E.2 OpenCode Non-Live Adapter Qualification — Complete

## Disposition

`EA-4E.2 OPENCODE ADAPTER = TASK-DELIVERY CORRECTED / CONTRACT RE-FROZEN CANDIDATE / NOT COMMITTED`

---

## 1. REPOSITORY

| Field | Value |
|-------|-------|
| Original commit | `4d39cf13a88312b7925ed1aad1da9a239f3fde20` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## 2. SOURCE

| Field | Value |
|-------|-------|
| Repository | `https://github.com/anomalyco/opencode` |
| Tag | `v1.18.11` |
| Commit | `012c2f57f976489d88bd4598a056b4bdcdd428ee` |
| Binary | `C:\Users\David\AppData\Local\hermes\node\node_modules\opencode-ai\bin\opencode.exe` |
| Version | `1.18.11` |
| SHA-256 | `578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35` |

---

## 3. AGENT PROFILE

| Field | Value |
|-------|-------|
| AGENT_ID | `hermes-ea4e-opencode-receiver` |
| AGENT_CONFIG | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home\.opencode\config.json` |
| FINAL_AGENT_OWNER | HERMES |
| TASK_AGENT_OVERRIDE | NO |
| TASK_MODEL_OVERRIDE | NO |

---

## 4. SECURITY

| Field | Value |
|-------|-------|
| GLOBAL_DEFAULT_DENY | YES |
| UNKNOWN_TOOL_POLICY | DENY |
| FILESYSTEM_WRITE | DENIED |
| SHELL | DENIED |
| TASK_NETWORK | DENIED |
| MCP | DENIED |
| SUBAGENT | DENIED |
| PERMISSION_POLICY_SHA256 | `9c4b23c8c9f0ad3202de21ba8c6ac81376906ecf708409c687b7e857ba5a9a1a` |

---

## 5. ISOLATION

| Field | Value |
|-------|-------|
| HERMES_RUNTIME_ROOT | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode` |
| OPENCODE_CWD | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode` |
| OPENCODE_EFFECTIVE_HOME | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home` |
| OPENCODE_CONFIG_DIR | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\config` |
| RUNTIME_ROOT_WITHIN_REPO | NO |
| ISOLATION_POLICY_SHA256 | `a95c4d61d0923edeb6a20397f75f143b7d09e805cc6b792958aaa2609de1228e` |

---

## 6. PROCESS

| Field | Value |
|-------|-------|
| PROCESS_PRIMITIVE | `subprocess.Popen` |
| SHELL | `False` |
| STDIN | `subprocess.DEVNULL` |

---

## 7. TRANSPORT CONTRACT

| Field | Value |
|-------|-------|
| FINAL_OPENCODE_TRANSPORT_CONTRACT_ID | `aa352bc847f59b556afd63fb3ac267de529c482ea6dc31a89e94d09681b18c06` |
| CANONICAL_FIELD_COUNT | 52 |

---

## 8. POST-LIVE TASK-DELIVERY DEFECT CORRECTION

### Live Failure Evidence (EA-4E.4)

| Field | Value |
|-------|-------|
| delegation_id | `ea4e4-delegation-003` |
| launch_attempt_id | `ea4e4-launch-003` |
| Task | `Return exactly: EA4E4_OPENCODE_LIVE_OK` |
| Task SHA-256 | `b85eb724ade8677fb6840fb3e71c6569a59857744d4818954e2f810e5fd386a3` |
| PID | 12112 |
| PROCESS_STARTED | YES |
| return_code | 0 |
| stdout | EMPTY |
| stderr | EMPTY |
| JSONL_PARSE | FAIL / NO OUTPUT |
| LIVE_MODEL_INVOCATIONS | 0 |

### Root Cause

The `execute()` method accepted `stdin_data` but never propagated it to the argv builder. The call chain was:
```
execute(stdin_data="...")
  -> prepare_invocation(stdin_data="...")
    -> build_argv("")   # BUG: task text not passed
      -> argv without task
```

### Fix Applied

Modified three methods:

1. **`execute()`**: Now accepts `task: str = ""` parameter and passes it to `prepare_invocation(task=task)`

2. **`prepare_invocation()`**: Now accepts `task: str = ""` parameter and passes it to `build_opencode_argv(task_message=task)`

3. **`build_opencode_argv()`**: Now accepts `task_message: str = ""` parameter and appends it to args if truthy

### Corrected Call Flow

```
execute(task="Return exactly: ...")
  -> prepare_invocation(task="Return exactly: ...")
    -> build_argv(task_message="Return exactly: ...")
      -> argv = ["opencode.exe", "run", ..., "Return exactly: ..."]
```

### Empty Task Policy

Empty task strings produce NO argv entry. The args tuple will not contain empty strings.

### Hostile Task Test

Verified that hostile tasks like `--model bad/model --agent attacker --auto` remain as a single positional argument. They cannot inject additional flags.

### Regression Tests Added

6 tests in `TestOpenCodeTaskDelivery`:
- `test_task_reaches_argv_exactly_once`
- `test_task_not_in_stdin`
- `test_empty_task_rejected_or_documented`
- `test_hostile_task_cannot_inject_flags`
- `test_execute_passes_task_to_argv`
- `test_prepare_invocation_includes_task`

---

## 9. HISTORICAL ID CLASSIFICATIONS

| ID | Classification |
|----|----------------|
| `8db3606d40c385699d577c57ccd5c29f30ac5abad7a32ef8ccd7f45dce787756` | HISTORICAL NARROW 7-FIELD CONTRACT ID |
| `f5847ff2dca31c97e66b1368903dd32f3875bf4d6c626f59b12367eeba1c280a` | HISTORICAL UNREPRODUCIBLE QUALIFICATION-REPORT VALUE |
| `01588d6dfcbaec4f476c94e095f406799753ea904cfeb67397c8e9de33f5728b` | INTERMEDIATE REMEDIATION CANDIDATE (superseded) |
| `9f5964920f2817d45fada970509928f6088d44b879d87acb1986b0ab68394434` | INTERMEDIATE CONTRACT-INTEGRITY REMEDIATION CANDIDATE (superseded) |
| `aa352bc847f59b556afd63fb3ac267de529c482ea6dc31a89e94d09681b18c06` | FINAL AUTHORITATIVE CONTRACT ID |

### Isolation Hash

- **HISTORICAL_ISOLATION_POLICY_SHA256**: `65339a2ad34f4815079d68d446237d637cfc53046522fbe4b64f5207a43e1aea` — ORIGINAL SERIALIZATION NOT RECOVERABLE
- **CURRENT_ISOLATION_POLICY_SHA256**: `a95c4d61d0923edeb6a20397f75f143b7d09e805cc6b792958aaa2609de1228e` — reproducible from current isolation material

---

## 10. DOCUMENTATION

- **Original HOLD**: `.hermes/handoffs/ea4e/EA-4E.2-OPENCODE-SECURITY-CONTRACT-HOLD.md`
- **Completion artifact**: this file
- **EA-4E.3 references**: `.hermes/handoffs/ea4e/EA-4E.3-KILO-NON-LIVE-ADAPTER-QUALIFICATION-COMPLETE.md`
- **EA-4E.4 HOLD**: `.hermes/handoffs/ea4e/EA-4E.4-OPENCODE-ONE-SHOT-LIVE-QUALIFICATION-RESULT.md`
- **EA-4E.4 model binding**: `.hermes/handoffs/ea4e/EA-4E.4-OPENCODE-TRUSTED-MODEL-BINDING.md`

---

## 11. GOVERNANCE

`EA-4E.2 OPENCODE ADAPTER = TASK-DELIVERY CORRECTED / CONTRACT RE-FROZEN CANDIDATE / NOT COMMITTED`

---

*Source trace: exact OpenCode 1.18.11 at `012c2f57f976489d88bd4598a056b4bdcdd428ee`.*
