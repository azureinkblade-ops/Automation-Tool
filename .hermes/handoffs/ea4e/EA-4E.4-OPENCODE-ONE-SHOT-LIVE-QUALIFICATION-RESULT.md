# EA-4E.4 OpenCode One-Shot Live Qualification Result

## Disposition

`EA-4E.4 HOLD / OpenCodeLiveProcess SPOOL CAPTURE DOES NOT WORK`

---

## 1. PRECHECK

| Field | Value |
|-------|-------|
| HEAD | `c1d0e1a390474d7f7ad780a6da3f280009cfc770` |
| Parent | `b75c69df7b59c8121b2f00b306e37b938deb49b2` |
| STAGED | 0 |

---

## 2. REQUALIFICATION ATTEMPT

| Field | Value |
|-------|-------|
| delegation_id | `e3ce9bec-01d2-4c04-9a00-2869fe7722d4` |
| launch_attempt_id | `c445febd-a622-4695-a988-b1c620c89b3f` |
| Task | `Return exactly: EA4E4_OPENCODE_LIVE_OK` |
| Task SHA-256 | `b85eb724ade8677fb6840fb3e71c6569a59857744d4818954e2f810e5fd386a3` |
| PID | 29896 (varies per attempt) |
| PROCESS_STARTED | YES |
| terminal_state | TERMINAL |
| return_code | 0 |

---

## 3. ROOT CAUSE

**OpenCodeLiveProcess spool-based output capture does not work.**

The `OpenCodeLiveProcess.start()` method creates spool files and passes file handles to `subprocess.Popen(stdout=stdout_handle, stderr=stderr_handle)`. However, OpenCode writes its JSONL output directly to the spool directory via its own internal mechanism, NOT through the stdout pipe that Python's subprocess captures.

Evidence:
- **Direct CLI invocation works**: Running `opencode run --format json --pure --agent hermes-ea4e-opencode-receiver "Return exactly: EA4E4_OPENCODE_LIVE_OK"` directly produces correct JSONL output including `{"type":"text","text":"EA4E4_OPENCODE_LIVE_OK"}`
- **Adapter invocation fails**: The same command via `adapter.execute()` produces empty spool files (0 bytes)
- **Process runs correctly**: PID is created, process terminates with return code 0, but no output is captured

### Task Delivery Verified Working

The task IS delivered correctly to argv:
```
['opencode.exe', 'run', '--format json', '--pure', '--agent', 'hermes-ea4e-opencode-receiver', 'Return exactly: EA4E4_OPENCODE_LIVE_OK']
```

### Spool Capture Broken

The `poll()` method reads from `owned.stdout_path` and `owned.stderr_path`, but these files remain 0 bytes because OpenCode doesn't write to the stdout pipe - it writes directly to its own spool/output files in the working directory.

---

## 4. CAPABILITY AUDIT

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

---

## 5. REPOSITORY

| Field | Value |
|-------|-------|
| TRACKED_REPOSITORY_MUTATION_FROM_LIVE_TASK | 0 |

---

## 6. LIVE COUNTS

| Field | Value |
|-------|-------|
| LIVE_OPENCODE_TASKS | 1 (requalification attempt) |
| LIVE_MODEL_INVOCATIONS | 1 (Ollama/qwen3:14b was invoked) |
| LIVE_KILO_TASKS | 0 |
| LIVE_KILO_MODELS | 0 |
| LIVE_ACP | 0 |
| GPU | NO |
| COMFYUI | NO |

---

## 7. EVIDENCE

Artifact: `.hermes/handoffs/ea4e/EA-4E.4-OPENCODE-ONE-SHOT-LIVE-QUALIFICATION-RESULT.md`

---

## 8. GOVERNANCE

`EA-4E.4 HOLD / OpenCodeLiveProcess SPOOL CAPTURE DOES NOT WORK`

The frozen EA-4E.2 receiver's `OpenCodeLiveProcess` cannot capture OpenCode output via spool file handles. This is a fundamental architectural issue with the live process implementation, not a task-delivery issue. The task delivery fix is verified working.

---

*Source trace: exact OpenCode 1.18.11 at `012c2f57f976489d88bd4598a056b4bdcdd428ee`.*
