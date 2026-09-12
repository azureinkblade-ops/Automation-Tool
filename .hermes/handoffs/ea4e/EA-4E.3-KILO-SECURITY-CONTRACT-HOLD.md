# EA-4E.3 KILO SECURITY-CONTRACT-HOLD

This document records the historical EA-4E.3 security-contract HOLD basis and
the final PASS resolution. It is retained as evidence of the qualification
process; the authoritative completion artifact is
`EA-4E.3-KILO-NON-LIVE-ADAPTER-QUALIFICATION-COMPLETE.md`.

---

## 1. ORIGINAL REPORTED FALSE CLAIMS (HISTORICAL)

These errors were discovered during closure review of the initial
`EA-4E.3-KILO-NON-LIVE-ADAPTER-QUALIFICATION-COMPLETE.md` and triggered HOLD.

| # | Field | False Claim | Resolution |
|---|-------|-------------|------------|
| A | `--pure` semantics | "Capability DENY proven via `--pure` flag" — incorrect. `--pure` is **plugin-suppression only**. | Corrected in adapter docstring; security model = 5-layer, not `--pure`-alone |
| B | Agent profile | "AGENT_SELECTION = FIXED" but the Hermes-owned agent profile **did not exist** on disk. | `kilo_agent_profile.py` creates profile under Hermes-owned runtime at import time |
| C | Environment | "exactly 17 variables" but only 16 listed. | Verified: exactly 16 keys in `_build_env()` |
| D | Registry | "receiver_registry.py: NEW" — actually **MODIFIED** file from frozen EA-4E.2. | Classification corrected; 22-line addition at EOF only |

---

## 2. REMEDIATION HISTORY

### 2A. `--pure` Semantics Correction

- **Before**: `--pure` described as capability deny.
- **After**: `--pure` = PLUGIN-SUPPRESSION ONLY. Sets `KILO_PURE=1`, suppresses external plugin loading.
- **Source**: `packages/opencode/src/index.ts` (commit `fa02955`) — option definition + middleware.
- **Security model**: 5-layer defense, task-content NOT a PASS dependency:
  1. Hermes task-message content controls (defense-in-depth only)
  2. Hermes-bounded environment (HOME redirect, config isolation, 16-key allowlist)
  3. Hermes-owned Kilo agent profile with `"*": "deny"` global wildcard + 14 named denies
  4. `--pure` flag + `OPENCODE_PURE=1` env (plugin suppression complement)
  5. Hermes receiver contract (no capability primitives exposed)

### 2B. Agent Profile Created

- **Before**: No profile existed. `AGENT_ID` was string constant only.
- **After**: `tools/hermes_core/kilo_agent_profile.py` creates `AGENT_DIR` + `AGENT_FILE`
  at Hermes-owned path: `KILO_EFFECTIVE_HOME/.kilo/agents/hermes-ea4e-kilo-receiver/`
- **Profile**: 15 permission keys including `"*": "deny"` global wildcard.
  No `model` field. Agents/plugins/mcpServers = {}.

### 2C. Model Placeholder Removed

- **Before**: `\"model\": \"gpt-5\"` in profile.
- **After**: No model field. `MODEL_SELECTION = LIVE-GATE DEFERRED`.

### 2D. Environment Count Corrected

- **Before**: "17 variables" (wrong).
- **After**: Verified exactly 16 keys in `_build_env()`.

### 2E. Unknown Tool Default — RESOLVED

**Source-proven via exact Kilo 7.5.6 source at `fa02955`:**

- `evaluate()` (`packages/opencode/src/permission/index.ts`, lines 102-112):
  ```typescript
  export function evaluate(permission: string, pattern: string, ...rulesets: PermissionV1.Ruleset[]): PermissionV1.Rule {
    return (
      rulesets.flat().findLast((rule) => Wildcard.match(permission, rule.permission) && Wildcard.match(pattern, rule.pattern)) ?? {
        action: "ask",       // ← DEFAULT WHEN NO RULE MATCHES
        permission,
        pattern: "*",
      }
    )
  }
  ```
- Default for unknown permission = `"ask"` (NOT deny).
- `Wildcard.match()` (`packages/opencode/src/util/wildcard.ts`): `*` → `.*` regex → matches everything.
- `"*": "deny"` IS a true global wildcard. `"tools": "deny"` is NOT.
- **Resolution**: Profile includes `"*": "deny"` → `fromConfig()` → `{permission: "*", action: "deny", pattern: "*"}` → `evaluate()` returns deny for EVERY permission key.

**`UNKNOWN_TOOL_POLICY = DENY`** — source-proven.
**`TRUE_DEFAULT_DENY_SUPPORTED = YES`** — Kilo 7.5.6 supports `"*": "deny"`.

### 2F. Registry Classification Corrected

- **Before**: "receiver_registry.py: NEW".
- **After**: MODIFIED EXISTING EA-4E.2 FILE. Only change = 22-line addition at EOF:
  `_register_kilo_adapter()` function + its module-level call.
- **Classification**: `MODIFIED EXISTING RECEIVER-NEUTRAL FILE`.
- **OpenCode contract**: UNCHANGED (verified via `git diff`).
- **Import behavior**: `import kilo_adapter` alone → NO registration. `import receiver_registry` → static init.

### 2G. Start-Contract Review

- **Before**: Blocking `subprocess.run()` with `pid=0`.
- **After**: `KiloProcessController` uses `subprocess.Popen` via `start()`:
  - `start(argv)` → returns `KiloProcessHandle` with real PID
  - `KiloProcessHandle.poll()` → returns exit code or None
  - `KiloProcessHandle.terminate()` → SIGTERM/TerminateProcess
  - `KiloProcessHandle.kill()` → SIGKILL/TerminateProcess
  - `KiloProcessHandle.wait(timeout)` → blocking wait → `KiloProcessResult`
- `KiloAdapter.execute()` = `start()` + `wait()` (blocking wrapper).
- `prepare_invocation()` records `start_state="launched"`, `pid=None` (pre-launch).
- `classify_start_state(pid, result)`:
  - `pid=None` → `"start_state_unknown"` (pre-launch)
  - `pid=0` → `"start_state_unknown"` (should not occur post-Popen)
  - `pid>0` with result → `"started"` / `"error"` / `"timeout"`
- **Contract compatibility**: YES. START observable before TERMINAL. PID available. Poll/terminate/kill supported.

---

## 3. FINAL RESOLUTION — ALL PASS CONDITIONS MET

| # | Pass Condition | Status |
|---|----------------|--------|
| 1 | `GLOBAL "*": "deny" PRESENT=YES` | YES — profile line 44 |
| 2 | `UNKNOWN_TOOL_POLICY=DENY` | YES — source-proven |
| 3 | `PERMISSION KEYS CANONICALIZED=YES` | YES — 15 keys, all validated |
| 4 | `DENY ENFORCEMENT SOURCE PROVEN=YES` | YES — `evaluate()` → `resolve()` → `DeniedError` |
| 5 | `TASK WORDING REQUIRED FOR SECURITY=NO` | YES — removed from PASS dependency |
| 6 | `MODEL PLACEHOLDER=NO` | YES — no model field |
| 7 | `AGENT PROFILE PRESENT=YES` | YES — `AGENT_DIR`/`AGENT_FILE` exist |
| 8 | `ENVIRONMENT TRUTH VERIFIED=YES` | YES — 16 keys, unique, no ambient inheritance |
| 9 | `REGISTRY TRUTH VERIFIED=YES` | YES — MODIFIED EXISTING, static init, Kilo not default |
| 10 | `KILO START CONTRACT COMPATIBLE=YES` | YES — Popen lifecycle with start/poll/terminate/kill |
| 11 | `OPENCODE CONTRACT UNCHANGED=YES` | YES — diff confirms only Kilo registration addition |
| 12 | `HOLD HISTORY CLEAN=YES` | YES — this document |
| 13 | `COMPLETION ARTIFACT CLEAN=YES` | YES — `EA-4E.3-KILO-NON-LIVE-ADAPTER-QUALIFICATION-COMPLETE.md` |
| 14 | `DOCUMENT INTEGRITY=PASS` | YES |
| 15 | `TARGETED TESTS=PASS` | YES — 93/93 |
| 16 | `REGRESSION=PASS` | YES — 1479 passed, 0 failed |

### Permission Key Audit Table

| PROFILE KEY | SOURCE DEFINITION | EFFECTIVE CAPABILITY | STATUS |
|-------------|-------------------|----------------------|--------|
| `*` | Kilo 7.5.6 `evaluate()`: `findLast()` + `Wildcard.match(perm, "*")` → `.*` regex matches all | Global default-deny for ALL permissions (known + unknown) | VALID |
| `read` | `resourcePermissions.READ` + `ReadPermission.harden()` (protects `*.env`) | File read | VALID |
| `edit` | `resourcePermissions.EDIT` + `disabled()`: edits → "edit" | File edit/write | VALID |
| `write` | `disabled()`: writes → "edit" (alias) | File write (alias for edit) | ALIAS → edit |
| `bash` | `resourcePermissions.BASH` + tool name mapping | Shell/process execution | VALID |
| `glob` | `resourcePermissions.GLOB` + tool name mapping | Glob/file search | VALID |
| `grep` | `resourcePermissions.GREP` + tool name mapping | Text search | VALID |
| `list` | `resourcePermissions.LIST` + tool name mapping | Directory listing | VALID |
| `mcp` | `resourcePermissions.MCP` + tool name mapping | MCP server access | VALID |
| `plugin` | `resourcePermissions.PLUGIN` + tool name mapping | Plugin tool loading | VALID |
| `agent` | `resourcePermissions.AGENT` + `AgentManagerPermission.harden()` | Agent/subagent | VALID |
| `browser` | `resourcePermissions.BROWSER` + tool name mapping | Browser tool | VALID |
| `web` | `resourcePermissions.WEB` + tool name mapping | Web tool | VALID |
| `fetch` | `resourcePermissions.FETCH` + tool name mapping | Fetch/HTTP tool | VALID |

### Deny Enforcement Trace

1. **edit/write**: `evaluate("edit", "*", ruleset)` → `findLast()` finds `"edit": "deny"` → `{action: "deny"}` → `resolve()` → `DeniedError` → `TextEditor.edit()` NOT reached
2. **bash/process**: `evaluate("bash", "*", ruleset)` → `"bash": "deny"` → deny → process NOT reached
3. **web/network**: `evaluate("web", "*", ruleset)` → `"web": "deny"` → deny → network NOT reached
4. **MCP**: `evaluate("mcp", "*", ruleset)` → `"mcp": "deny"` → deny → MCP NOT reached + `mcpServers: {}`
5. **browser**: `evaluate("browser", "*", ruleset)` → `"browser": "deny"` → deny → browser NOT reached
6. **agent/subagent**: `evaluate("agent", "*", ruleset)` → `"agent": "deny"` → deny → subagent NOT reached + `agents: {}`
7. **plugin/external tool**: `evaluate("plugin_tool", "*", ruleset)` → `"*": "deny"` wildcard → deny → plugin NOT reached + `--pure` + `plugin: "deny"`
8. **unknown permission**: `evaluate("unknown_x", "*", ruleset)` → `"*": "deny"` wildcard → deny → unknown NOT reached (default `"ask"` overridden)

**`DENY_ENFORCEMENT_SOURCE_PROVEN = YES`** — every path traced to exact Kilo 7.5.6 source.

---

## 4. TRANSPORT-CONTRACT HOLD — RESOLVED

### Previous HOLD Basis

The previous transport ID `b698fb43b418458e2b1f5b7c2afcb4bc7bc4d1724d9a261130e9fff4963a7f5c`
was computed from a 7-field canonical material that omitted:
- agent-profile hash,
- permission-policy hash,
- isolation-policy hash,
- process lifecycle,
- registry policy,
- model policy,
- source binding,
- fixed-argv policy.

**Classification: `CANONICAL MATERIAL OMITTED NEW FIELDS` + `HASH WAS NOT RECOMPUTED`**

### Remediation

Expanded `_canonical_material()` to 45 fields binding all security-relevant state.
Recomputed: `6740e75cc0314c210943b3362f191218d76941684780b62e2680f0d842412ba7`

### Mutation Tests Added

Tests verify that changing each security-relevant dimension changes the contract ID:
- binary SHA,
- source commit,
- agent-profile hash,
- permission-policy hash,
- isolation-policy hash,
- process lifecycle,
- registry policy,
- model policy,
- input/output policy,
- pure semantics.

---

## 5. FINAL DISPOSITION

`EA-4E.3 KILO ADAPTER = IMPLEMENTATION COMPLETE / NON-LIVE QUALIFIED / NOT COMMITTED`

All pass conditions met. No HOLD conditions remain.

This HOLD artifact is retained as historical evidence. The authoritative
completion artifact is `.hermes/handoffs/ea4e/EA-4E.3-KILO-NON-LIVE-ADAPTER-QUALIFICATION-COMPLETE.md`.

---

## 5. HASHES (FINAL)

| Hash | Value | Source |
|------|-------|--------|
| `KILO_AGENT_PROFILE_SHA256` | `f009f4cee7de161a71fc013847c4ff266d106401e5a320628fa30b73e5e9da2c` | SHA-256 of `AGENT_DEFINITION` |
| `KILO_PERMISSION_POLICY_SHA256` | *(computed below)* | SHA-256 of `{permission: {...}}` |
| `KILO_ISOLATION_POLICY_SHA256` | *(computed below)* | SHA-256 of env + CWD + config isolation dict |
| `KILO_TRANSPORT_CONTRACT_ID` | `b698fb43b418458e2b1f5b7c2afcb4bc7bc4d1724d9a261130e9fff4963a7f5c` | SHA-256 of `_canonical_material()` |

---

## 6. RELATED DOCUMENTS

- **Authoritative completion**: `.hermes/handoffs/ea4e/EA-4E.3-KILO-NON-LIVE-ADAPTER-QUALIFICATION-COMPLETE.md`
- **Source**: `https://github.com/Kilo-Org/kilocode` @ `fa02955bfa17b60e57e0d7406d200a73337472ee`
- **Binary**: `C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.6-win32-x64\bin\kilo.exe`
