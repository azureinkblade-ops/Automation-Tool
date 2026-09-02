# EA-4E.4 OpenCode Trusted Model-Binding Qualification

## Disposition

`EA-4E.4 TRUSTED MODEL BINDING = PASS / LIVE TASK NOT YET EXECUTED`

---

## 1. GOVERNING HEAD

| Field | Value |
|-------|-------|
| HEAD | `b75c69df7b59c8121b2f00b306e37b938deb49b2` |
| Parent | `338ed900a2a3dcf381063e3ddc33b4f9f58ca9a6` |
| STAGED | 0 |

---

## 2. FROZEN OPENCODE CONTRACT

| Field | Value |
|-------|-------|
| OPENCODE_TRANSPORT_CONTRACT_ID | `2348c9e484ed1e20f958c7af4238d596a5d7cda8bae87b57d1450ffd499244d7` |
| PERMISSION_POLICY_SHA256 | `9c4b23c8c9f0ad3202de21ba8c6ac81376906ecf708409c687b7e857ba5a9a1a` |
| ISOLATION_POLICY_SHA256 | `a95c4d61d0923edeb6a20397f75f143b7d09e805cc6b792958aaa2609de1228e` |

---

## 3. SOURCE PRECEDENCE

From exact OpenCode 1.18.11 source inspection:

### Model Selection Precedence (highest to lowest):

1. **CLI `--model` flag** (if present, always wins)
2. **Agent profile model** (`cfg.agent[name].model`)
3. **Config `model` field** (top-level `config.json` / `opencode.jsonc`)
4. **Provider default model** (fallback)

### Source Evidence:

**`packages/opencode/src/cli/cmd/run.ts`** (RunCommand handler):
```typescript
const model = pick(args.model)  // Returns undefined if no --model
```

**`packages/opencode/src/agent/agent.ts`** (Agent state):
```typescript
for (const [key, value] of Object.entries(cfg.agent ?? {})) {
    if (value.model) item.model = Provider.parseModel(value.model)
    // ...
}
```

**`packages/opencode/src/config/config.ts`** (Config loading):
```typescript
result = mergeConfig(result, yield* loadFile(path.join(Global.Path.config, "config.json"), env))
```

**`packages/opencode/src/provider/provider.ts`** (Provider resolution):
```typescript
const resolved = yield* provider.getModel(model.providerID, model.modelID)
```

### Config Path Resolution:

OpenCode uses `Global.Path.config` which resolves to:
- `OPENCODE_CONFIG_DIR` environment variable if set
- Otherwise `~/.config/opencode/` (or platform equivalent)

---

## 4. PROVIDER

| Field | Value |
|-------|-------|
| PROVIDER | `ollama` |
| MODEL | `qwen3:14b` |
| CREDENTIAL_AVAILABLE | YES (local server, no API key required) |
| SOURCE | Hermes-owned isolated config |

---

## 5. BINDING

| Field | Value |
|-------|-------|
| MODEL_BINDING_OWNER | HERMES |
| MODEL_BINDING_LOCATION | `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\config\config.json` |
| MODEL_BINDING_WITHIN_REPO | NO |
| AMBIENT_USER_CONFIG_USED | NO |
| PROJECT_CONFIG_USED | NO |
| MODEL_BINDING_LAYER | CONFIG (via OPENCODE_CONFIG_DIR redirect + agent model) |

### Binding Mechanism:

The OpenCode adapter sets `OPENCODE_CONFIG_DIR` to the Hermes-owned isolated runtime path. This redirects OpenCode's config loading from `~/.config/opencode/` to our isolated directory.

The isolated `config.json` contains:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "name": "Ollama",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://localhost:11434/v1"
      },
      "models": {
        "qwen3:14b": {
          "name": "qwen3:14b"
        }
      }
    }
  },
  "model": "ollama/qwen3:14b",
  "agent": {
    "hermes-ea4e-opencode-receiver": {
      "model": "ollama/qwen3:14b"
    }
  }
}
```

---

## 6. BINDING ID

**EA4E4_MODEL_BINDING_ID**: `2b45284eec7c86a6debf92f0774e21e9ad7d2c6d4009192f645149633bd45046`

### Canonical Material (non-secret):

```json
{
  "opencode_transport_contract_id": "2348c9e484ed1e20f958c7af4238d596a5d7cda8bae87b57d1450ffd499244d7",
  "provider_id": "ollama",
  "model_id": "qwen3:14b",
  "selection_mechanism": "Hermes-owned OPENCODE_CONFIG_DIR redirect",
  "config_location": "C:\\Users\\David\\AppData\\Local\\Hermes\\runtime\\ea4e\\opencode\\config\\config.json",
  "config_location_within_repo": false,
  "ambient_user_config_used": false,
  "project_config_used": false,
  "credential_mechanism": "local Ollama server (no API key required)",
  "task_model_override": false,
  "task_provider_override": false,
  "task_agent_override": false,
  "agent_id": "hermes-ea4e-opencode-receiver",
  "prior_session_inheritance_prevented": true
}
```

---

## 7. OVERRIDE AUDIT

| Field | Value |
|-------|-------|
| TASK_MODEL_OVERRIDE | NO |
| TASK_PROVIDER_OVERRIDE | NO |
| TASK_AGENT_OVERRIDE | NO |
| PRIOR_SESSION_MODEL_INHERITANCE | NO |

### Session Contamination Prevention:

OpenCode's `opencode run` creates a fresh session by default (no `--continue` or `--session` flags). The frozen EA-4E.2 argv does not include `--continue` or `--session`, so each invocation starts fresh without inheriting prior session state.

---

## 8. STATIC EFFECTIVE-MODEL RESOLUTION

**STATIC_EFFECTIVE_MODEL_RESOLUTION**: PASS

### Resolution Trace:

1. Frozen argv: `opencode run --format json --pure --agent hermes-ea4e-opencode-receiver <task>`
2. No `--model` flag → `pick(args.model)` returns `undefined`
3. Agent `hermes-ea4e-opencode-receiver` is selected via `--agent`
4. Agent has `model: "ollama/qwen3:14b"` in isolated config
5. Provider `ollama` is configured with `baseURL: http://localhost:11434/v1`
6. Model resolves to `ollama/qwen3:14b`

### Verification:

- Ollama is running (verified via `curl http://localhost:11434/api/tags`)
- Model `qwen3:14b` is loaded and available
- No API key required (local server)
- No task-controlled flags in argv

---

## 9. FROZEN CONTRACT

| Field | Value |
|-------|-------|
| OPENCODE_TRANSPORT_CONTRACT_ID | `2348c9e484ed1e20f958c7af4238d596a5d7cda8bae87b57d1450ffd499244d7` (UNCHANGED) |
| FROZEN_RECEIVER_CONTRACT_CHANGED | NO |

The model binding is entirely external to the frozen EA-4E.2 receiver contract. No adapter code was modified.

---

## 10. LIVE COUNTS

| Field | Value |
|-------|-------|
| LIVE_OPENCODE_TASKS | 0 |
| LIVE_MODEL_INVOCATIONS | 0 |
| LIVE_KILO_TASKS | 0 |
| LIVE_KILO_MODELS | 0 |
| LIVE_ACP | 0 |

---

## 11. REPOSITORY

| Field | Value |
|-------|-------|
| HEAD | `b75c69df7b59c8121b2f00b306e37b938deb49b2` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

The model binding configuration is outside the repository (in `LOCALAPPDATA/Hermes/runtime/`).

---

## 12. GOVERNANCE

`EA-4E.4 TRUSTED MODEL BINDING = PASS / LIVE TASK NOT YET EXECUTED`

The live task budget (1 OpenCode task) remains unused. The model binding is statically proven and ready for the one-shot live qualification.

---

*Source trace: exact OpenCode 1.18.11 at `012c2f57f976489d88bd4598a056b4bdcdd428ee`. Model selection precedence derived from `packages/opencode/src/cli/cmd/run.ts`, `packages/opencode/src/agent/agent.ts`, and `packages/opencode/src/config/config.ts`.*
