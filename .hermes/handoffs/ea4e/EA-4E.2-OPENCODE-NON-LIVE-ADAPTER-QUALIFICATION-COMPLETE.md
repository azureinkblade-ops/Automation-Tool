# EA-4E.2 OpenCode Non-Live Adapter Qualification — Complete

## Disposition

`EA-4E.2 OPENCODE ADAPTER = SECURITY-QUALIFIED / CONTRACT-INTEGRITY REMEDIATED / NOT COMMITTED`

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
| FINAL_OPENCODE_TRANSPORT_CONTRACT_ID | `9f5964920f2817d45fada970509928f6088d44b879d87acb1986b0ab68394434` |
| CANONICAL_FIELD_COUNT | 51 |

---

## 8. POST-FREEZE CONTRACT-INTEGRITY CORRECTION

### Original Frozen State

The original commit `4d39cf13a88312b7925ed1aad1da9a239f3fde20` contained an internal inconsistency:

| Source | Value |
|--------|-------|
| **Adapter exported** `OPENCODE_TRANSPORT_CONTRACT_ID` | `8db3606d40c385699d577c57ccd5c29f30ac5abad7a32ef8ccd7f45dce787756` |
| **Qualification artifact** claimed | `f5847ff2dca31c97e66b1368903dd32f3875bf4d6c626f59b12367eeba1c280a` |
| **HOLD artifact** claimed | `f5847ff2dca31c97e66b1368903dd32f3875bf4d6c626f59b12367eeba1c280a` |

### Root Cause

The adapter's `_canonical_material()` function returned only 7 fields (adapter_version, binary_sha256, binary_version, input_delivery, pure, structured_output, transport) that did NOT bind the security-qualified state. The `f5847ff2…` value reported in artifacts was unrecoverable from the committed code.

### Remediation

Expanded `_canonical_material()` to 51 fields binding all security-relevant state. The new authoritative ID is:

**`9f5964920f2817d45fada970509928f6088d44b879d87acb1986b0ab68394434`**

### Historical ID Classifications

- `8db3606d40c385699d577c57ccd5c29f30ac5abad7a32ef8ccd7f45dce787756` = **HISTORICAL NARROW 7-FIELD CONTRACT ID**
- `f5847ff2dca31c97e66b1368903dd32f3875bf4d6c626f59b12367eeba1c280a` = **HISTORICAL UNREPRODUCIBLE QUALIFICATION-REPORT VALUE**
- `01588d6dfcbaec4f476c94e095f406799753ea904cfeb67397c8e9de33f5728b` = **INTERMEDIATE REMEDIATION CANDIDATE** (superseded by final)

### Isolation Hash

- **HISTORICAL_ISOLATION_POLICY_SHA256**: `65339a2ad34f4815079d68d446237d637cfc53046522fbe4b64f5207a43e1aea` — ORIGINAL SERIALIZATION NOT RECOVERABLE
- **CURRENT_ISOLATION_POLICY_SHA256**: `a95c4d61d0923edeb6a20397f75f143b7d09e805cc6b792958aaa2609de1228e` — reproducible from current isolation material

### Mutation Tests Added

19 tests verify `SECURITY_RELEVANT_CHANGE -> CONTRACT_ID_CHANGE`:
- binary SHA, source commit, permission-policy hash, isolation-policy hash, agent ID, model-selection policy, process primitive, pure semantics, input delivery, registry policy, filesystem-write policy, shell policy, task-network policy, MCP policy, subagent policy, environment policy, process lifecycle, start policy, terminate policy

---

## 9. DOCUMENTATION

- **Original HOLD**: `.hermes/handoffs/ea4e/EA-4E.2-OPENCODE-SECURITY-CONTRACT-HOLD.md`
- **Completion artifact**: this file
- **EA-4E.3 references**: `.hermes/handoffs/ea4e/EA-4E.3-KILO-NON-LIVE-ADAPTER-QUALIFICATION-COMPLETE.md`

---

## 10. GOVERNANCE

`EA-4E.2 OPENCODE ADAPTER = SECURITY-QUALIFIED / CONTRACT-INTEGRITY REMEDIATED / NOT COMMITTED`

---

*Source trace: exact OpenCode 1.18.11 at `012c2f57f976489d88bd4598a056b4bdcdd428ee`.*
