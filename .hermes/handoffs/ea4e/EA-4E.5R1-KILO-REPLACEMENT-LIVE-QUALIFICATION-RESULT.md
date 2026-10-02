# EA-4E.5R1 Kilo Replacement One-Shot Governed Live Qualification

## Disposition

`EA-4E.5R1 KILO REPLACEMENT ONE-SHOT GOVERNED LIVE QUALIFICATION = PASS / EVIDENCE COMPLETE / NOT COMMITTED`

---

## 1. Governing Commit

| Field | Value |
|-------|-------|
| HEAD | `27783723aab58222f95ec1e3cc4bf6655c79ce76` |
| Parent | `9b71c22c32ca98a05afb3450841fec06a6dc8041` |

## 2. Historical Attempt #1 (Preserved)

| Field | Value |
|-------|-------|
| EA-4E.5 LIVE ATTEMPT #1 | **HOLD / RESULT PARSE FAILURE** |
| Task | `Return exactly: EA4E5_KILO_LIVE_OK` |
| Task SHA | `798e978801da076d0cb8031cd02253a87de5b02a217a05e3604f57312c32a148` |
| PID | 32596 |
| Return Code | 0 |
| Output Capture | PASS |
| Result Parse | FAIL |

### Historical Accounting

| Category | Count |
|----------|-------|
| Original Governed Model Invocations | 1 |
| Non-Governed Diagnostic Model Invocations | 1 |
| **Total Previous Kilo Model Invocations** | **2** |

## 3. EA-4E.5R1 Replacement Authority

| Field | Value |
|-------|-------|
| EA4E5R1_GOVERNED_KILO_TASKS_MAX | 1 |
| EA4E5R1_MODEL_INVOCATIONS_MAX | 1 |
| EA4E5R1_RETRY_BUDGET | 0 |
| Delegation ID | `1cb05ea4-0c22-42c5-b05e-1def86ecbd3f` |
| Launch Attempt ID | `3d9a1fbe-3b1f-448a-a69a-84d47ad5fc6e` |

## 4. Kilo Binary Identity

| Field | Value |
|-------|-------|
| VERSION | 7.5.9 |
| PATH | `C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.9-win32-x64\bin\kilo.exe` |
| SIZE | 170498048 |
| SHA256 | `ec8737555947a145f3418962890f539b6b175ba3de125689f7ccb197d0004a36` |
| UPSTREAM_REPO | Kilo-Org/kilocode |
| UPSTREAM_TAG | v7.5.9 |
| UPSTREAM_COMMIT | 24b4b9fef7cbbc877007b3939053efb6fac1b38f |

`KILO_BINARY_IDENTITY=PASS`

## 5. Contract

| Hash | Value |
|------|-------|
| KILO_TRANSPORT_CONTRACT_ID | `c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500` |
| KILO_MODEL_BINDING_ID | `b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544` |
| KILO_PERMISSION_POLICY_SHA256 | `87e74bf20efc07c1b89e1dff5e8e75fba08f96f18677afdbbac411ce4cc87cf3` |
| KILO_ISOLATION_POLICY_SHA256 | `d93b5fdcfe41f7e988898eb894f0856121e4dd688092ff2915e395da765744e9` |
| KILO_AGENT_PROFILE_SHA256 | `f009f4cee7de161a71fc013847c4ff266d106401e5a320628fa30b73e5e9da2c` |

`KILO_CONTRACT=PASS`

## 6. Model Binding

| Field | Value |
|-------|-------|
| MODEL_ARGUMENT | `kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` |
| SELECTION_MECHANISM | FIXED_ARGV |
| MODEL_FLAG | --model |
| TASK_MODEL_OVERRIDE | NO |
| TASK_PROVIDER_OVERRIDE | NO |
| AMBIENT_OVERRIDE | NO |
| SESSION_OVERRIDE | NO |
| FALLBACK | NO |
| DYNAMIC_ROUTING | NO |

## 7. Task

| Field | Value |
|-------|-------|
| task_text | `Return exactly: EA4E5_KILO_LIVE_OK` |
| task_sha256 | `798e978801da076d0cb8031cd02253a87de5b02a217a05e3604f57312c32a148` |
| TASK_DELIVERED_EXACTLY_ONCE | YES |
| TASK_DUPLICATED | NO |

## 8. Start-State Persistence Chain

| Field | Value |
|-------|-------|
| LAUNCH_ATTEMPT_RECORDED | YES |
| PROCESS_STARTED | YES |
| PID | 5512 |
| START_RESULT_PERSISTED | YES |
| EXECUTING_PROJECTION_COMMITTED | YES |

`START_STATE_CHAIN=PASS`

## 9. Process Ownership

| Field | Value |
|-------|-------|
| RETURN_CODE | 0 |
| TERMINAL_STATE | completed |
| TIMED_OUT | NO |
| TERMINATED | NO |
| KILLED | NO |
| DETACHED_UNMANAGED_CHILD | NO |

## 10. Argv

```
kilo run --format json --pure --agent hermes-ea4e-kilo-receiver --model kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free Return exactly: EA4E5_KILO_LIVE_OK
```

| Field | Value |
|-------|-------|
| MODEL_FLAG_COUNT | 1 |
| MODEL_ARGUMENT_COUNT | 1 |
| TASK_POSITION_COUNT | 1 |
| AUTO_FLAG_PRESENT | NO |
| TASK_CONTROLLED_MODEL_FLAG | NO |

## 11. Output Capture

| Field | Value |
|-------|-------|
| STDOUT_BYTES | 1854 |
| STDERR_BYTES | 92 |
| OUTPUT_CAPTURE | PASS |
| CAPTURE_ERROR | NONE |

## 12. Result Parser

| Field | Value |
|-------|-------|
| RESULT_PARSE | PASS |
| NORMALIZED_TEXT | `EA4E5_KILO_LIVE_OK` |
| RESULT_TEXT_MATCH | YES |
| KILO_TEXT_SCHEMA | NESTED_PART_TEXT_WITH_TOP_LEVEL_BACKCOMPAT |

## 13. Result Persistence Chain

| Field | Value |
|-------|-------|
| PROCESS_TERMINAL | YES |
| OUTPUT_CAPTURED | YES |
| RESULT_PARSED | YES |
| NORMALIZED_RESULT_CREATED | YES |
| DELEGATION_RESULT_CREATED | YES |
| RESULT_PERSISTED | YES |
| EVIDENCE_PERSISTED | YES |
| RESULT_RETURNED_TO_HERMES | YES |

`RESULT_PERSISTENCE_CHAIN=PASS`

## 14. Security / Capability Audit

| Field | Value |
|-------|-------|
| TOOL_CALL_COUNT | 0 |
| PERMISSION_REQUEST_COUNT | 0 |
| DENIED_TOOL_ATTEMPTS | 0 |
| FILESYSTEM_READ_ATTEMPTS | 0 |
| FILESYSTEM_WRITE_ATTEMPTS | 0 |
| SHELL_ATTEMPTS | 0 |
| TASK_NETWORK_ATTEMPTS | 0 |
| MCP_ATTEMPTS | 0 |
| SUBAGENT_ATTEMPTS | 0 |
| POLICY_WIDENING | NO |

`UNAUTHORIZED_CAPABILITY_EXECUTION=NO`

## 15. Model Accounting

### Current Replacement (EA-4E.5R1)

| Field | Value |
|-------|-------|
| EA4E5R1_PROMPT_INVOCATIONS | 1 |
| EA4E5R1_MODEL_INVOCATIONS | 1 |
| MODEL_PROVIDER | nvidia |
| MODEL_ID | nemotron-3-nano-omni-30b-a3b-reasoning:free |
| INPUT_TOKENS | 4975 |
| OUTPUT_TOKENS | 15 |
| REASONING_TOKENS | 28 |
| TOTAL_TOKENS | 7194 |
| COST | 0 |
| MODEL_SUBSTITUTION | NO |
| MODEL_FALLBACK | NO |

### Cumulative Historical Accounting

| Category | Count |
|----------|-------|
| Original Governed Model Invocations (EA-4E.5) | 1 |
| Non-Governed Diagnostic Model Invocations | 1 |
| Replacement Governed Model Invocations (EA-4E.5R1) | 1 |
| **Total Kilo Model Invocations Across EA-4E.5 History** | **3** |

## 16. Repository Mutation

| Field | Value |
|-------|-------|
| NEW_TRACKED_REPOSITORY_MUTATION_FROM_TASK | 0 |
| UNRELATED_PREEXISTING_WIP_PRESERVED | YES |

## 17. Evidence Artifact

| Field | Value |
|-------|-------|
| Artifact | `.hermes/handoffs/ea4e/EA-4E.5R1-KILO-REPLACEMENT-LIVE-QUALIFICATION-RESULT.md` |
| State | UNSTAGED / UNCOMMITTED |
| SHA256 | `f6030826f8d820d1c87ef62783139b8620e9857feb1f1b923d45cd1211886e21` |

## 18. Repository

| Field | Value |
|-------|-------|
| HEAD | `27783723aab58222f95ec1e3cc4bf6655c79ce76` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## GOVERNANCE

`EA-4E.5R1 KILO REPLACEMENT ONE-SHOT GOVERNED LIVE QUALIFICATION = PASS / EVIDENCE COMPLETE / NOT COMMITTED`

`KILO RECEIVER = LIVE QUALIFIED AGAINST 7.5.9`

`EA-4E.5 = LIVE QUALIFIED / EVIDENCE COMMIT REQUIRED`

`EA4E5R1_EVIDENCE_SHA256=f6030826f8d820d1c87ef62783139b8620e9857feb1f1b923d45cd1211886e21`
