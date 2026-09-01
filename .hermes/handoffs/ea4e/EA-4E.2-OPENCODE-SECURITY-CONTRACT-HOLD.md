# EA-4E.2 OpenCode Security-Contract Hold — Effective-Home Isolation Resolution

## Status

`EA-4E.2 = HOLD / ISOLATION IMPLEMENTATION MISMATCH → RESOLVED`

Reason: The initial implementation used `Path(__file__).resolve().parents[2] / ".hermes"` as `HERMES_RUNTIME_ROOT`, which resolved to `<repo>/.hermes` — inside the Automation Tool repository. This contradicted the qualification claim `CWD_OUTSIDE_AUTOMATION_TOOL_REPO=YES`. The runtime root has been relocated to `LOCALAPPDATA/Hermes/runtime/ea4e/opencode`, a genuinely out-of-repo path. The double `.hermes` path in `default_opencode_config()` was also corrected (`runtime = HERMES_RUNTIME_ROOT` instead of `runtime = HERMES_RUNTIME_ROOT / ".hermes" / "runtime" / "ea4e" / "opencode"`).

---

## Precheck

- Worktree HEAD: `49c49f1` (parent `0a71bc6`)
- Exact OpenCode source: `anomalyco/opencode` tag `v1.18.11`, commit `012c2f57f976489d88bd4598a056b4bdcdd428ee`
- Installed binary SHA-256: `578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35`
- STAGED=0 (confirmed)
- Commit: NOT AUTHORIZED, Push: NO

---

## PATH CORRECTION (critical fix)

**Old (incorrect):**
- `HERMES_RUNTIME_ROOT = Path(__file__).resolve().parents[2] / ".hermes"` → `<repo>/.hermes` (INSIDE repository)
- `OPENCODE_CWD = HERMES_RUNTIME_ROOT` → inside repository
- `runtime = HERMES_RUNTIME_ROOT / ".hermes" / "runtime" / "ea4e" / "opencode"` → double `.hermes` path

**New (correct):**
- `HERMES_RUNTIME_ROOT = Path(os.environ["LOCALAPPDATA"]) / "Hermes" / "runtime" / "ea4e" / "opencode"` → `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode` (OUTSIDE repository)
- `OPENCODE_CWD = HERMES_RUNTIME_ROOT` → outside repository
- `runtime = HERMES_RUNTIME_ROOT` → single path, no double `.hermes`

**`FINAL_RUNTIME_ROOT_WITHIN_REPO = NO`**
**`OPENCODE_CWD_WITHIN_REPO = NO`**

---

## EFFECTIVE HOME POLICY (corrected)

- **`OPENCODE_EFFECTIVE_HOME`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home`
- **`OPENCODE_CONFIG_DIR`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\config`
- **`OPENCODE_HOME_OPENCODE`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home\.opencode`
- **`OPENCODE_CWD`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode`

---

## ENVIRONMENT (corrected)

The environment tuple now contains each name exactly once:

| Variable | Value |
|---|---|
| `OPENCODE_TEST_HOME` | `<OPENCODE_EFFECTIVE_HOME>` |
| `HOME` | `<OPENCODE_EFFECTIVE_HOME>` |
| `USERPROFILE` | `<OPENCODE_EFFECTIVE_HOME>` |
| `OPENCODE_CONFIG_DIR` | `<OPENCODE_CONFIG_DIR>` |
| `OPENCODE_DISABLE_PROJECT_CONFIG` | `1` |
| `OPENCODE_PURE` | `1` |
| `SYSTEMROOT` | `C:\WINDOWS` |
| `WINDIR` | `C:\WINDOWS` |
| `TEMP` | `C:\Users\David\AppData\Local\Temp` |
| `TMP` | `C:\Users\David\AppData\Local\Temp` |
| `PATH` | `<bin_dir>;<system PATH>` |

**`ENVIRONMENT_NAMES_UNIQUE = YES`**
**`AMBIENT_OPENCODE_ENV_INHERITED = NO`**

---

## CONFIG WALK (corrected)

- **`CONFIG_WALK_START`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode`
- **`CONFIG_WALK_STOP`** = `/` (no git repo in Hermes runtime)
- **`CONFIG_WALK_ANCESTORS`** = Hermes runtime path upward to root — no `.opencode/` in ancestor chain
- **`CWD_CONFIG_WALK_HERMES_ONLY = YES`**
- **`AUTOMATION_TOOL_REPO_OPENCODE_VISIBLE = NO`** — cwd is outside the Automation Tool repository
- **`NORMAL_USER_HOME_OPENCODE_VISIBLE = NO`** — `os.homedir()` returns the Hermes-owned path

---

## CUSTOM AGENT CONFIG

- **`CUSTOM_AGENT_CONFIG_PRESENT`** = YES — `config.json` created at `<OPENCODE_HOME_OPENCODE>/config.json`
- **`CUSTOM_AGENT_CONFIG_PATH`** = `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home\.opencode\config.json`
- **`CUSTOM_AGENT_CONFIG_HASH`** = `9c4b23c8c9f0ad3202de21ba8c6ac81376906ecf708409c687b7e857ba5a9a1a`
- **`FINAL_AGENT_OWNER`** = HERMES

---

## PERMISSION POLICY

- **`PERMISSION_POLICY_SHA256`** = `9c4b23c8c9f0ad3202de21ba8c6ac81376906ecf708409c687b7e857ba5a9a1a`
- Hashed policy == written/bound policy == effective custom agent policy

---

## ISOLATION POLICY (recomputed)

- **`FINAL_ISOLATION_POLICY_SHA256`** = `65339a2ad34f4815079d68d446237d637cfc53046522fbe4b64f5207a43e1aea`

---

## FINAL TRANSPORT CONTRACT (recomputed)

- **`FINAL_OPENCODE_TRANSPORT_CONTRACT_ID`** = `f5847ff2dca31c97e66b1368903dd32f3875bf4d6c626f59b12367eeba1c280a`
- **`FINAL CONTRACT MATERIAL HASH VERIFIED`** = YES

---

## HOLD DECISION

`EA-4E.2 SECURITY HOLD RESOLVED`

The implementation mismatch (runtime root inside repository) has been corrected. All closure conditions are now met:

| Condition | Value |
|---|---|
| `FINAL_RUNTIME_ROOT_WITHIN_REPO` | NO |
| `OPENCODE_CWD_WITHIN_REPO` | NO |
| `CWD_CONFIG_WALK_HERMES_ONLY` | YES |
| `NORMAL_USER_HOME_CONFIG_VISIBLE` | NO |
| `AUTOMATION_TOOL_CONFIG_VISIBLE` | NO |
| `AMBIENT_OPENCODE_ENV_INHERITED` | NO |
| `ENVIRONMENT_NAMES_UNIQUE` | YES |
| `CUSTOM_AGENT_CONFIG_PRESENT` | YES |
| `FINAL_AGENT_OWNER` | HERMES |
| `PERMISSION POLICY IMPLEMENTED` | YES |
| `STDIN CLOSED` | YES |
| `TASK POSITIONAL EXACTLY ONCE` | YES |
| `TARGETED TESTS` | PASS (37 adapter, 14 registry) |
| `FULL REGRESSION` | PASS (1386, 104 subtests) |

---

## REGRESSION

- `tests/hermes_core/test_opencode_adapter.py`: **37 passed**
- `tests/hermes_core/test_receiver_adapter.py`: **14 passed**
- `tests/hermes_core/` full suite: **1386 passed, 104 subtests passed**

All regressions pass after the runtime root correction.

---

## CONTRACT

Final canonical material and contract ID computed from the corrected implementation.

---

## REPOSITORY

- HEAD: `49c49f1`
- Staged: 0
- Commit: NOT AUTHORIZED
- Push: NO

---

## GOVERNANCE

`EA-4E.2 = HOLD / ISOLATION IMPLEMENTATION MISMATCH → RESOLVED`

The closure audit correctly identified the CWD isolation mismatch. The runtime root has been relocated from `<repo>/.hermes` to `LOCALAPPDATA/Hermes/runtime/ea4e/opencode`, the double `.hermes` path has been corrected, environment name uniqueness has been guaranteed, and all tests pass. The HOLD is resolved.

### Notes

- The initial implementation's use of `Path(__file__).resolve().parents[2] / ".hermes"` was incorrect because it placed the runtime root inside the repository. The corrected implementation uses `os.environ["LOCALAPPDATA"] / "Hermes" / "runtime"` which is guaranteed to be outside all repositories and worktrees.
- The `OPENCODE_TEST_HOME` variable is used in the adapter environment. It is production-honored in OpenCode v1.18.11 source (unconditional getter in `global.ts`).
- Remote account config and platform policy layers remain as higher-trust layers outside Hermes control.
- EA-4E.3 may proceed only after explicit authorization.