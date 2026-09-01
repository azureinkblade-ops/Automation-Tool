# EA-4E.2 OpenCode Non-Live Adapter Qualification — Complete

## Disposition

`EA-4E.2 OPENCODE ADAPTER = IMPLEMENTATION COMPLETE / NON-LIVE QUALIFIED / NOT COMMITTED`

---

## Starting HEAD

`49c49f11cb300efeef3e94091b96ac8beb68cb18`

## Frozen Hashes

- **R11 SHA-256**: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- **EA-4E design SHA-256**: `9c7338c3bace17dddca0acebfb3da04e2a60531ef162ea5fa5aac8ad4e150be1`

## Binary Identity

- **Path**: `C:\Users\David\AppData\Local\hermes\node\node_modules\opencode-ai\bin\opencode.exe`
- **Version**: `1.18.11`
- **SHA-256**: `578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35`
- **Format**: PE32+ (Bun-compiled)

## Exact Source Binding

- **Repository**: `anomalyco/opencode`
- **Tag**: `v1.18.11`
- **Commit**: `012c2f57f976489d88bd4598a056b4bdcdd428ee`

---

## DENY ENFORCEMENT

All capability-level deny enforcement is proven from exact v1.18.11 source:

- `FILESYSTEM_WRITE = DENIED` — `yield* ctx.ask` short-circuits on `DeniedError`
- `SHELL = DENIED` — `yield* ctx.ask` short-circuits on `DeniedError`
- `TASK_NETWORK = DENIED` — `yield* ctx.ask` short-circuits on `DeniedError`
- `MCP EXECUTION = DENIED` — `--pure` + deny blocks execution
- `SUBAGENT = DENIED` — `yield* ctx.ask` short-circuits on `DeniedError`
- `UNKNOWN_TOOL_POLICY = DENY` — trailing `"*": "deny"` via `findLast`

**Central invariant**: `DENY -> PermissionV1.DeniedError -> TOOL EXECUTION NOT REACHED`

---

## EFFECTIVE-HOME ISOLATION

### Runtime Root (corrected)

The runtime root was relocated from `<repo>/.hermes` (inside the repository) to a genuinely out-of-repo path:

- **`HERMES_RUNTIME_ROOT`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode`
- Derived from `os.environ["LOCALAPPDATA"] / "Hermes" / "runtime" / "ea4e" / "opencode"`
- **`FINAL_RUNTIME_ROOT_WITHIN_REPO`** = NO
- **`OPENCODE_CWD_WITHIN_REPO`** = NO

### Global.Path.home and os.homedir

- **`Global.Path.home`** = `process.env.OPENCODE_TEST_HOME ?? os.homedir()`
  - `GLOBAL_PATH_HOME = <OPENCODE_EFFECTIVE_HOME>` — `OPENCODE_TEST_HOME` is set explicitly in the adapter env
  - `GLOBAL_PATH_HOME_HERMES_OWNED = YES`
- **`os.homedir()`** checks `HOME`, `USERPROFILE`, `HOMEDRIVE+HOMEPATH`
  - `OS_HOMEDIR = <OPENCODE_EFFECTIVE_HOME>` — `HOME` and `USERPROFILE` are set explicitly in the adapter env
  - `OS_HOMEDIR_HERMES_OWNED = YES`
- `OPENCODE_TEST_HOME` is a production-honored runtime getter in `global.ts`, not test-only.

### Effective Home Policy

- **`OPENCODE_EFFECTIVE_HOME`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home`
- **`OPENCODE_CONFIG_DIR`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\config`
- **`OPENCODE_HOME_OPENCODE`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home\.opencode`
- **`OPENCODE_CWD`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode`

### Config Source Audit

| Source | Effective Location | Trust Owner |
|---|---|---|
| Global.Path.config | `<OPENCODE_CONFIG_DIR>/opencode` | Hermes (via `OPENCODE_CONFIG_DIR`) |
| Global.Path.home/.opencode | `<OPENCODE_EFFECTIVE_HOME>/.opencode` | Hermes (via `OPENCODE_TEST_HOME` + `HOME`) |
| OPENCODE_CONFIG | Adapter-controlled | Hermes |
| OPENCODE_CONFIG_CONTENT | Adapter-controlled | Hermes |
| Project config files | Disabled (`OPENCODE_DISABLE_PROJECT_CONFIG=1`) | Hermes |
| Project `.opencode/` | Disabled + out-of-repo cwd | Hermes |
| Remote account config | Remote server | NOT HERMES — requires authentication isolation |
| Managed config | System admin layer | HIGHER TRUST — administrator-owned |

### HOME `.opencode/` Consequence

- **`HOME_OPENCODE_PATH`** = `<OPENCODE_EFFECTIVE_HOME>/.opencode`
- **`HOME_OPENCODE_OWNER`** = HERMES
- **`NORMAL_USER_HOME_OPENCODE_VISIBLE`** = NO — `os.homedir()` returns the Hermes-owned path
- **`CWD_CONFIG_WALK`** = HERMES OWNED ONLY — out-of-repo Hermes runtime root contains no `.opencode/` directories

### Project Config Disable

- **`OPENCODE_DISABLE_PROJECT_CONFIG`** = `1` (explicitly set in adapter env)
- **`AUTOMATION_TOOL_REPO_PROJECT_CONFIG_VISIBLE`** = NO — cwd is outside the Automation Tool repository
- Both defense layers (flag + out-of-repo cwd) are active.

---

## AMBIENT ENVIRONMENT VARIABLES

The adapter constructs a bounded environment tuple. Ambient `HOME`, `USERPROFILE`, `OPENCODE_TEST_HOME`, and `OPENCODE_CONFIG_DIR` are NOT inherited — they are explicitly bound to Hermes-owned values. Each name appears exactly once in the final environment tuple.

- **`AMBIENT OPENCODE ENV INHERITED`** = NO
- **`ENVIRONMENT_NAMES_UNIQUE`** = YES

---

## AGENT IDENTITY

- **`AGENT_ID`** = `hermes-ea4e-opencode-receiver`
- The fixed argv includes `--agent hermes-ea4e-opencode-receiver`.
- Delegated task cannot change it because the adapter controls `args.agent`.
- **`TASK_AGENT_OVERRIDE`** = NO
- Custom agent `value.permission` is merged last in `agent.ts`, so the agent's own permission field takes precedence over `defaults` and `cfg.permission`.
- **`FINAL_AGENT_OWNER`** = HERMES
- **`AMBIENT SAME-NAME AGENT COLLISION`** = BLOCKED — only the Hermes-owned `.opencode/` agent definition is loaded under the redirected effective home.
- **`CUSTOM_AGENT_CONFIG_PRESENT`** = YES — `config.json` at `<OPENCODE_HOME_OPENCODE>/config.json`
- **`CUSTOM_AGENT_CONFIG_PATH`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home\.opencode\config.json`
- **`CUSTOM_AGENT_CONFIG_HASH`** = `9c4b23c8c9f0ad3202de21ba8c6ac81376906ecf708409c687b7e857ba5a9a1a`

---

## PERMISSION POLICY

Canonical effective policy:

- `read`: allow (safe allowlist)
- `edit`: deny
- `write`: deny
- `apply_patch`: deny
- `bash`: deny
- `webfetch`: deny
- `websearch`: deny
- `task`: deny
- `skill`: deny
- `mcp`: deny
- `browser`: deny
- `*`: deny (wildcard)

**`FINAL_PERMISSION_OWNER`** = HERMES

- **`PERMISSION_POLICY_SHA256`** = `9c4b23c8c9f0ad3202de21ba8c6ac81376906ecf708409c687b7e857ba5a9a1a`
- Hashed policy == written/bound policy == effective custom agent policy

---

## ISOLATION POLICY

- **`FINAL_ISOLATION_POLICY_SHA256`** = `65339a2ad34f4815079d68d446237d637cfc53046522fbe4b64f5207a43e1aea`

Covers: effective-home policy, os.homedir policy, global config root, cwd policy, project-config policy, ambient env policy, trusted custom agent identity, stdin policy, runtime root policy.

---

## INPUT CONTRACT

- **`RUN_INPUT_MECHANISM`** = POSITIONAL
- **`TASK_PRESENT_IN_ARGV`** = YES — `args.message` is a single joined positional string
- **`TASK_ARG_COUNT`** = 1
- **`STDIN`** = `subprocess.DEVNULL` — zero bytes written, no task JSON on stdin
- **`STDIN_BYTES_WRITTEN`** = 0
- **`SECOND TASK INPUT CHANNEL`** = NO
- **`MAX_POSITIONAL_TASK_BYTES`** = 32768
- **`TASK_CONTROLS_FLAGS`** = NO — task text follows fixed flags
- **`OPENCODE_CAN_READ_AMBIENT_STDIN`** = NO
- **`--agent hermes-ea4e-opencode-receiver`** is in the fixed argv as a pinned flag

---

## OUTPUT CONTRACT

- **`RUN_JSON_FRAMING`** = JSONL (one JSON object per line)
- **`TEXT_EVENT_SEMANTICS`** = LAST TEXT EVENT — successive `type: "text"` events represent streaming deltas/independent parts; the final assistant text is the last `type: "text"` event with non-empty `text`
- **`NORMALIZATION`** = `text_events[-1]["text"].strip()`

---

## MCP

- **`NORMAL_USER_MCP_CONFIG_VISIBLE`** = NO — all config roots under Hermes control; `--pure` + `OPENCODE_DISABLE_PROJECT_CONFIG` prevent ambient MCP loading
- **`MCP EXECUTION`** = DENIED — permission-level MCP deny remains as defense in depth
- **`PURE_MCP_EFFECT`** = NOT DISABLED by `--pure` alone, but isolated by effective-home boundary

---

## REMOTE / MANAGED CONFIG

- **`REMOTE_ACCOUNT_CAN_REDEFINE_AGENT`** = NO for local receiver
- **`REMOTE_ACCOUNT_CAN_WEAKEN_PERMISSION`** = NO for local receiver
- **`WINDOWS_MANAGED_CONFIG_PATH`** = NONE
- **`WINDOWS_MANAGED_CONFIG_CAN_REDEFINE_AGENT`** = NOT APPLICABLE
- If a higher-trust administrator layer exists, it is classified as administrator-owned.

---

## FOCUSED TEST RESULTS

- **`tests/hermes_core/test_opencode_adapter.py`**: **37 passed**
- **`tests/hermes_core/test_receiver_adapter.py`**: **14 passed**
- **`ZERO FAILURES`**

---

## FULL REGRESSION

- **`tests/hermes_core/`**: **1386 passed, 104 subtests passed**
- **Warnings**: 1 (PytestCache access denied — pre-existing, not test-related)
- **Zero failures**

---

## LIVE-CAPABILITY AUDIT

- **`LIVE_OPENCODE_TASKS`** = 0
- **`LIVE_OPENCODE_MODELS`** = 0
- **`LIVE_ACP`** = 0
- **`KILO`** = 0
- **`PRODUCTION_ROUTING`** = OFF
- **`DEFAULT_OPENCODE_RECEIVER`** = NO
- **`FAILOVER`** = OFF
- **`SCHEDULER`** = OFF
- **`GPU`** = NO
- **`COMFYUI`** = NO

---

## FINAL CANONICAL CONTRACT

### Contract Material

- **Receiver ID**: `opencode-cli-agent`
- **Adapter Version**: `ea4e.2`
- **Binary Path**: `C:\Users\David\AppData\Local\hermes\node\node_modules\opencode-ai\bin\opencode.exe`
- **Binary SHA-256**: `578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35`
- **Binary Version**: `1.18.11`
- **Source Tag**: `v1.18.11`
- **Source Commit**: `012c2f57f976489d88bd4598a056b4bdcdd428ee`
- **Transport**: `opencode-run`
- **Fixed CLI Policy**: `run --format json --pure --agent hermes-ea4e-opencode-receiver`
- **Trusted Agent ID**: `hermes-ea4e-opencode-receiver`
- **Permission Policy SHA-256**: `9c4b23c8c9f0ad3202de21ba8c6ac81376906ecf708409c687b7e857ba5a9a1a`
- **Isolation Policy SHA-256**: `65339a2ad34f4815079d68d446237d637cfc53046522fbe4b64f5207a43e1aea`
- **Effective-Home Policy**: `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home`
- **Global Config Root**: `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\config`
- **CWD Policy**: out-of-repo LOCALAPPDATA/Hermes runtime
- **Environment Policy**: `HOME`, `USERPROFILE`, `OPENCODE_TEST_HOME`, `OPENCODE_CONFIG_DIR`, `OPENCODE_DISABLE_PROJECT_CONFIG`, `OPENCODE_PURE` (unique names)
- **Positional Input Limit**: 32768 bytes
- **Stdin Closed**: YES (`subprocess.DEVNULL`)
- **JSONL Framing**: JSONL
- **JSONL Normalization**: last text event
- **Model Selection Policy**: trusted config / live-gate deferred

### Final Contract ID

**`FINAL_OPENCODE_TRANSPORT_CONTRACT_ID`** = `f5847ff2dca31c97e66b1368903dd32f3875bf4d6c626f59b12367eeba1c280a`

**`FINAL CONTRACT MATERIAL HASH VERIFIED`** = YES

---

## CORRECTION NOTES

The closure audit identified a critical isolation mismatch in the initial implementation:

1. **Runtime root inside repository**: `HERMES_RUNTIME_ROOT = Path(__file__).resolve().parents[2] / ".hermes"` resolved to `<repo>/.hermes`, which is inside the Automation Tool repository. Fixed to `os.environ["LOCALAPPDATA"] / "Hermes" / "runtime" / "ea4e" / "opencode"`.

2. **Double `.hermes` path**: `default_opencode_config()` constructed `runtime = HERMES_RUNTIME_ROOT / ".hermes" / "runtime" / "ea4e" / "opencode"`, creating `.hermes/.hermes/runtime/...`. Fixed to `runtime = HERMES_RUNTIME_ROOT`.

3. **Environment name duplicates**: `env_names` included `HOME`, `USERPROFILE`, `OPENCODE_TEST_HOME`, `OPENCODE_CONFIG_DIR` then skipped and re-appended them. Fixed to only include system vars in `env_names` and explicitly bind each isolation variable exactly once.

---

## DOCUMENTATION

- **Updated**: `.hermes/handoffs/ea4e/EA-4E.2-OPENCODE-SECURITY-CONTRACT-HOLD.md` — resolved HOLD with corrected paths
- **Created**: `.hermes/handoffs/ea4e/EA-4E.2-OPENCODE-NON-LIVE-ADAPTER-QUALIFICATION-COMPLETE.md` (this artifact)

---

## REPOSITORY STATE

- **HEAD**: `49c49f1`
- **Staged**: 0
- **Commit**: NOT AUTHORIZED
- **Push**: NO
- **EA-4E.2 files**: preserved as untracked (no staged changes)
- **Unrelated WIP**: preserved

---

## GOVERNANCE

`EA-4E.2 OPENCODE ADAPTER = IMPLEMENTATION COMPLETE / NON-LIVE QUALIFIED / NOT COMMITTED`

All closure conditions proven:

| Condition | Value |
|---|---|
| `FINAL_RUNTIME_ROOT_WITHIN_REPO` | NO |
| `OPENCODE_CWD_WITHIN_REPO` | NO |
| `CWD_CONFIG_WALK` | HERMES OWNED ONLY |
| `NORMAL_USER_HOME_CONFIG_VISIBLE` | NO |
| `AUTOMATION_TOOL_CONFIG_VISIBLE` | NO |
| `AMBIENT_OPENCODE_ENV_INHERITED` | NO |
| `ENVIRONMENT_NAMES_UNIQUE` | YES |
| `CUSTOM_AGENT_CONFIG_PRESENT` | YES |
| `FINAL_AGENT_OWNER` | HERMES |
| `PERMISSION POLICY IMPLEMENTED` | YES |
| `STDIN CLOSED` | YES |
| `POSITIONAL TASK ONLY` | YES |
| `ZERO FAILURES` | YES — 37 adapter tests, 14 registry tests, 1386 full suite |
| `NO LIVE INVOCATIONS` | YES |
| `NO COMMIT/PUSH` | YES |

### Notes

- `OPENCODE_TEST_HOME` is production-honored in OpenCode v1.18.11 source (unconditional getter in `global.ts`).
- Remote account config and platform policy layers (MDM) remain as higher-trust layers outside Hermes control.
- EA-4E.3 may proceed only after explicit authorization.
- This artifact is NOT committed and NOT pushed.