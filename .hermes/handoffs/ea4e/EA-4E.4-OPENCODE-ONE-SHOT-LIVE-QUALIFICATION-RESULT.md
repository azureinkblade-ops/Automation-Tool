# EA-4E.4 OpenCode One-Shot Live Qualification Result

## Disposition

`EA-4E.4 OPENCODE FINAL LIVE REQUALIFICATION = PASS / COMMITTED / FROZEN / NOT PUSHED`

---

## Historical Attempts

### Attempt 1: Original (Pre-Remediation)

| Field | Value |
|-------|-------|
| delegation_id | `ea4e4-delegation-003` |
| launch_attempt_id | `ea4e4-launch-003` |
| Task | `Return exactly: EA4E4_OPENCODE_LIVE_OK` |
| PID | 12112 |
| return_code | 0 |
| RESULT | HOLD (spool capture broken) |

**Historical diagnosis at the time of Attempt 1:** The original file-handle capture path (`stdout=stdout_handle`) produced empty spool files. Later investigation determined the precise internal cause was not proven; the failing boundary was the original file-handle capture path itself.

### Attempt 2: Post-PIPE (Pre-Parser)

| Field | Value |
|-------|-------|
| delegation_id | `e3ce9bec-01d2-4c04-9a00-2869fe7722d4` |
| launch_attempt_id | `c445febd-a622-4695-a988-b1c620c89b3f` |
| PID | 35372 |
| return_code | 0 |
| STREAM_CAPTURE | PASS |
| JSONL_PARSE | FAIL |
| RESULT | HOLD (parser incompatible) |

**Root cause:** Parser expected flat `{"type":"text","text":"..."}` but OpenCode emitted nested `{"type":"text","part":{"text":"..."}}`.

---

## Final Qualification

### PIPE Remediation

Capture subsequently verified working. Implemented in commit `ef4a9e8704ca472f2b6d7f304e94293b51188dd0`.

### Parser Remediation

Nested `part.text` schema qualified offline and committed. Implemented in commit `39fe9620498e1bbcec5565dba440184403060f3c`.

### Final Post-Parser Live Attempt

PASS.

---

## 1. PRECHECK

| Field | Value |
|-------|-------|
| HEAD | `39fe9620498e1bbcec5565dba440184403060f3c` |
| Parent | `6537384f6d488496b3f34f032b9d423f5cb08a1e` |
| STAGED | 0 |

---

## 2. FROZEN TRANSPORT

| Field | Value |
|-------|-------|
| OPENCODE_TRANSPORT_CONTRACT_ID | `192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f` |
| PERMISSION_POLICY_SHA256 | `9c4b23c8c9f0ad3202de21ba8c6ac81376906ecf708409c687b7e857ba5a9a1a` |
| ISOLATION_POLICY_SHA256 | `a95c4d61d0923edeb6a20397f75f143b7d09e805cc6b792958aaa2609de1228e` |

---

## 3. MODEL BINDING

| Field | Value |
|-------|-------|
| EA4E4_MODEL_BINDING_ID | `cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371` |
| PROVIDER | `ollama` |
| MODEL | `qwen3:14b` |
| PROVIDER_MODEL_CHANGED | NO |

---

## 4. PROVIDER PREFLIGHT

| Field | Value |
|-------|-------|
| OLLAMA_REACHABLE | YES |
| qwen3:14b_AVAILABLE | YES |
| AUTHENTICATION_REQUIRED | NO |

---

## 5. AUTHORITY

| Field | Value |
|-------|-------|
| delegation_id | `d0809f7d-3084-499e-8c1e-2694c9a13332` |
| launch_attempt_id | `78f86581-e3ec-434b-a5f0-97a5d92c9ab9` |
| LAUNCH_ATTEMPT_RECORDED | YES |

---

## 6. START

| Field | Value |
|-------|-------|
| PROCESS_STARTED | YES |
| PID | 4324 |
| START_RESULT_PERSISTED | YES |
| EXECUTING_PROJECTION_COMMITTED | YES |

---

## 7. PROCESS

| Field | Value |
|-------|-------|
| return_code | 0 |
| timed_out | NO |
| terminated | NO |
| killed | NO |

---

## 8. PIPE CAPTURE

| Field | Value |
|-------|-------|
| STDOUT_TOTAL_BYTES | 944 |
| STDOUT_RETAINED_BYTES | 944 |
| STDOUT_TRUNCATED | NO |
| STDERR_TOTAL_BYTES | 96 |
| STDERR_RETAINED_BYTES | 96 |
| STDERR_TRUNCATED | NO |
| STDOUT_READER_ALIVE_AT_RESULT | NO |
| STDERR_READER_ALIVE_AT_RESULT | NO |
| STDOUT_READER_ERROR | NONE |
| STDERR_READER_ERROR | NONE |
| STREAM_CAPTURE | PASS |
| STREAM_FINALIZATION | PASS |

---

## 9. JSONL PARSE

| Field | Value |
|-------|-------|
| JSONL_PARSE | PASS |
| NORMALIZED_TEXT | `EA4E4_OPENCODE_LIVE_OK` |
| RESULT_TEXT_MATCH | YES |

---

## 10. RESULT CHAIN

| Field | Value |
|-------|-------|
| PROCESS_TERMINAL | YES |
| STREAMS_FINALIZED | YES |
| JSONL_PARSE | PASS |
| NORMALIZED_RESULT | `EA4E4_OPENCODE_LIVE_OK` |
| DELEGATION_RESULT_CREATED | YES |
| RESULT_PERSISTED | YES |
| EVIDENCE_PERSISTED | YES |
| RESULT_RETURNED_TO_HERMES | YES |

---

## 11. SECURITY AUDIT

| Field | Value |
|-------|-------|
| TOOL_CALL_COUNT | 0 |
| PERMISSION_REQUEST_COUNT | 0 |
| DENIED_TOOL_ATTEMPTS | 0 |
| FILESYSTEM_WRITE_OCCURRED | NO |
| SHELL_EXECUTION_OCCURRED | NO |
| TASK_NETWORK_TOOL_USED | NO |
| MCP_EXECUTION_OCCURRED | NO |
| SUBAGENT_EXECUTION_OCCURRED | NO |
| POLICY_WIDENING | NO |

---

## 12. ACCOUNTING

| Field | Value |
|-------|-------|
| POST_PARSER_PROMPT_INVOCATIONS | 1 |
| MODEL_INVOCATION | YES (tokens: 8185 total, 25 input, 32 output) |

---

## 13. REPOSITORY

| Field | Value |
|-------|-------|
| TRACKED_REPOSITORY_MUTATION_FROM_TASK | 0 |

---

## 14. GOVERNANCE

`EA-4E.4 OPENCODE FINAL LIVE REQUALIFICATION = PASS / COMMITTED / FROZEN / NOT PUSHED`

The post-parser final live requalification has passed all qualification gates:
- PIPE capture verified working (944 bytes stdout captured)
- Nested-text parser verified working (correctly parsed `EA4E4_OPENCODE_LIVE_OK`)
- Full result-persistence chain verified
- Security audit clean
- No unauthorized capability execution

The EA-4E.4 OpenCode governed receiver is qualified for production activation pending separate authorization.

---

## Milestone Summary

| Milestone | Status | Commit |
|-----------|--------|--------|
| Task-delivery correction | FROZEN | `c1d0e1a390474d7f7ad780a6da3f280009cfc770` |
| Output-capture remediation (PIPE) | COMMITTED | `ef4a9e8704ca472f2b6d7f304e94293b51188dd0` |
| Model-binding evidence refresh | COMMITTED | `6537384f6d488496b3f34f032b9d423f5cb08a1e` |
| Parser compatibility (nested-text) | COMMITTED | `39fe9620498e1bbcec5565dba440184403060f3c` |
| Final live qualification evidence | COMMITTED | `83ad1f576e8a077da7c97eace18c6e7acc665749` |

---

*Source trace: exact OpenCode 1.18.11 at `012c2f57f976489d88bd4598a056b4bdcdd428ee`.*
