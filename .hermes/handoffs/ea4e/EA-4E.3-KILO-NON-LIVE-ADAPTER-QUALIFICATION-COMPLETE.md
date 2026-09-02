# EA-4E.3 Kilo Non-Live Adapter Qualification — Complete

## Disposition

`EA-4E.3 KILO ADAPTER = IMPLEMENTATION COMPLETE / NON-LIVE QUALIFIED / NOT COMMITTED`

---

## 1. REPOSITORY

| Field | Value |
|-------|-------|
| HEAD | `4d39cf13a88312b7925ed1aad1da9a239f3fde20` |
| Parent | `49c49f11cb300efeef3e94091b96ac8beb68cb18` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

EA-4E.2 remains: FROZEN / COMMITTED / NON-LIVE QUALIFIED / NOT PUSHED

---

## 2. SOURCE

| Field | Value |
|-------|-------|
| Repository | `https://github.com/Kilo-Org/kilocode` |
| Tag | `v7.5.6` |
| Commit | `fa02955bfa17b60e57e0d7406d200a73337472ee` |
| Binary | `C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.6-win32-x64\bin\kilo.exe` |
| Version | `7.5.6` |
| Size | `170337792` |
| SHA-256 | `e78c0006cad1e65238e8c5b32ee937128c474f07b8d3b3fa3d0b24c32ab79860` |
| SOURCE_BINDING | PROVEN |

---

## 3. AGENT PROFILE

| Field | Value |
|-------|-------|
| AGENT_ID | `hermes-ea4e-kilo-receiver` |
| AGENT_FILE | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo\home\.kilo\agents\hermes-ea4e-kilo-receiver\hermes-ea4e-kilo-receiver.jsonc` |
| AGENT_DIR | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo\home\.kilo\agents\hermes-ea4e-kilo-receiver` |
| AGENT_PROFILE_SHA256 | `f009f4cee7de161a71fc013847c4ff266d106401e5a320628fa30b73e5e9da2c` |
| MODEL_FIELD | ABSENT |
| MODEL_SELECTION | LIVE-GATE DEFERRED |
| AGENT_OWNER | HERMES |

---

## 4. SECURITY

| Field | Value |
|-------|-------|
| GLOBAL_DEFAULT_DENY | YES — `"*": "deny"` wildcard |
| UNKNOWN_TOOL_POLICY | DENY — wildcard overrides Kilo default `ask` |
| FILESYSTEM_WRITE | DENIED — `edit`, `write` → deny |
| SHELL | DENIED — `bash` → deny |
| TASK_NETWORK | DENIED — `web`, `fetch` → deny |
| MCP | DENIED — `mcp` → deny |
| BROWSER | DENIED — `browser` → deny |
| SUBAGENT | DENIED — `agent` → deny |
| ARBITRARY_TOOL | DENIED — wildcard `"*": "deny"` |
| TASK_CONTENT_REQUIRED_FOR_SECURITY | NO |
| PERMISSION_POLICY_SHA256 | `0687421bd7d2718caeb0671ce7a586fcf7c8fe6e7a4f4472001bf886d625538a` |

### Permission Keys (14, all deny)

| Key | Status |
|-----|--------|
| `*` | VALID — global default-deny |
| `read` | VALID |
| `edit` | VALID |
| `write` | ALIAS → edit |
| `bash` | VALID |
| `glob` | VALID |
| `grep` | VALID |
| `list` | VALID |
| `mcp` | VALID |
| `plugin` | VALID |
| `agent` | VALID |
| `browser` | VALID |
| `web` | VALID |
| `fetch` | VALID |

### Enforcement Trace

`evaluate(perm, "*", ruleset)` → `findLast()` finds matching deny rule → `resolve()` returns deny → `DeniedError` thrown → execution NOT reached. For unknown permissions, the `"*": "deny"` wildcard matches via `Wildcard.match(perm, "*")` → `.*` regex → matches everything.

`DENY_ENFORCEMENT_SOURCE_PROVEN = YES`

---

## 5. ENVIRONMENT

| Field | Value |
|-------|-------|
| ACTUAL_ENV_KEY_COUNT | 16 |
| ENV_NAMES_UNIQUE | YES |
| AMBIENT_INHERITED | NO |
| PARENT_SECRETS | 0 |

Keys: `HOME`, `HOMEDRIVE`, `HOMEPATH`, `KILO_CONFIG_DIR`, `KILO_HOME`, `KILO_PURE`, `OPENCODE_CONFIG_DIR`, `OPENCODE_DISABLE_PROJECT_CONFIG`, `OPENCODE_PURE`, `OPENCODE_TEST_HOME`, `PATH`, `PROCESSOR_ARCHITECTURE`, `SYSTEMROOT`, `TEMP`, `TMP`, `USERPROFILE`

---

## 6. ISOLATION

| Field | Value |
|-------|-------|
| HERMES_RUNTIME_ROOT | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo` |
| KILO_CWD | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo` |
| KILO_EFFECTIVE_HOME | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo\home` |
| KILO_CONFIG_DIR | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo\config` |
| RUNTIME_ROOT_WITHIN_REPO | NO |
| ISOLATION_POLICY_SHA256 | `5a739b621c4444837de8316bb88d17b66a2f87a9222e1e8e6ef28b0fff7e2ce6` |

---

## 7. PROCESS

| Field | Value |
|-------|-------|
| PROCESS_PRIMITIVE | `subprocess.Popen` |
| START_METHOD | YES |
| PID_BEFORE_TERMINAL | YES |
| POLL/WAIT | YES |
| TERMINATE | YES |
| KILL | YES |
| STDIN | `subprocess.DEVNULL` |
| SHELL | `False` |
| START_CONTRACT_COMPATIBLE | YES |

---

## 8. REGISTRY

| Field | Value |
|-------|-------|
| CLASSIFICATION | MODIFIED EXISTING EA-4E.2 FILE |
| SELF_REGISTRATION | NO |
| STATIC_INIT | YES — `_register_kilo_adapter()` at module init |
| KILO_REGISTERED | YES |
| KILO_DEFAULT | NO |
| PRODUCTION_ENABLED | NO |
| OPENCODE_UNCHANGED | YES — `git diff HEAD` empty |

---

## 9. OPENCODE FROZEN CONTRACT

| Field | Value |
|-------|-------|
| OPENCODE_TRANSPORT_CONTRACT_ID | `9f5964920f2817d45fada970509928f6088d44b879d87acb1986b0ab68394434` |
| CONTRACT_UNCHANGED | YES — `git diff HEAD` empty |

Note: The original EA-4E.2 commit `4d39cf13a88312b7925ed1aad1da9a239f3fde20` had an internal inconsistency between its adapter-exported ID (`8db3606d...`) and its qualification artifacts (`f5847ff2...`). The contract was remediated to bind all security-relevant state, producing the authoritative ID `9f596492...`.

---

## 10. KILO TRANSPORT CONTRACT

| Field | Value |
|-------|-------|
| KILO_TRANSPORT_CONTRACT_ID | `6740e75cc0314c210943b3362f191218d76941684780b62e2680f0d842412ba7` |
| CANONICAL_FIELD_COUNT | 45 |
| CANONICAL_CONTRACT | == IMPLEMENTED TRUTH |

### Canonical Fields (sorted)

`adapter_version`, `agent_id`, `agent_profile_sha256`, `ambient_inherited`, `binary_path`, `binary_sha256`, `binary_version`, `config_isolation`, `config_root`, `cwd`, `cwd_within_repo`, `default_receiver`, `effective_home`, `environment_key_count`, `environment_keys`, `failover`, `fixed_argv_note`, `fixed_argv_policy`, `global_default_deny`, `input_delivery`, `isolation_policy_sha256`, `model_selection_policy`, `permission_policy_sha256`, `process_primitive`, `production_routing`, `profile_model_field`, `pure`, `pure_semantics`, `receiver_id`, `registry_policy`, `runtime_root`, `runtime_root_within_repo`, `shell`, `source_commit`, `source_repository`, `source_tag`, `start_lifecycle`, `stdin_policy`, `structured_output`, `termination_policy`, `timeout_default`, `timeout_max`, `timeout_min`, `transport`, `unknown_tool_policy`

---

## 11. TESTS

| Field | Value |
|-------|-------|
| KILO_TEST_COMMAND | `python -m pytest tests/hermes_core/test_kilo_adapter.py -v` |
| KILO_TOTAL_UNIQUE | 99 passed, 0 failed |
| HERMES_CORE_COMMAND | `python -m pytest tests/hermes_core/ -q` |
| FULL_HERMES_CORE | 1485 passed, 104 subtests |

---

## 12. DOCUMENTATION

| Field | Value |
|-------|-------|
| HOLD_ARTIFACT | `.hermes/handoffs/ea4e/EA-4E.3-KILO-SECURITY-CONTRACT-HOLD.md` |
| COMPLETION_ARTIFACT | `.hermes/handoffs/ea4e/EA-4E.3-KILO-NON-LIVE-ADAPTER-QUALIFICATION-COMPLETE.md` |
| DOCUMENT_INTEGRITY | PASS |

---

## 13. LIVE AUDIT

| Field | Value |
|-------|-------|
| LIVE_KILO_TASKS | 0 |
| LIVE_KILO_MODELS | 0 |
| LIVE_ACP | 0 |
| DEFAULT_KILO_RECEIVER | NO |
| AUTOMATIC_FAILOVER | OFF |
| PRODUCTION_ROUTER | OFF |
| GPU | NO |
| COMFYUI | NO |

---

## 14. GOVERNANCE

`EA-4E.3 KILO ADAPTER = IMPLEMENTATION COMPLETE / NON-LIVE QUALIFIED / NOT COMMITTED`

All pass conditions met. No HOLD conditions remain.

---

*Source trace: exact Kilo 7.5.6 at `fa02955bfa17b60e57e0d7406d200a73337472ee`. Permission enforcement via `packages/opencode/src/permission/index.ts` (`evaluate()` + `findLast()`) and `packages/opencode/src/util/wildcard.ts` (`match()` → `.*` for `*`).*
