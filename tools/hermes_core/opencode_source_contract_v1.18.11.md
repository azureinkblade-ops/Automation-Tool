# EA-4E.2 OpenCode 1.18.11 Source-Contract Inspection Report

Source binding: **exact v1.18.11 tag** of `anomalyco/opencode`, commit
`012c2f57f976489d88bd4598a056b4bdcdd428ee` (tag `v1.18.11`).

All findings below are sourced from that exact revision only. Current upstream
`main` is NOT used.

---

## SOURCE BINDING

- **UPSTREAM_REPOSITORY**: `https://github.com/anomalyco/opencode`
- **RELEASE_VERSION**: `1.18.11`
- **RELEASE_TAG**: `v1.18.11`
- **TAG_COMMIT_SHA**: `012c2f57f976489d88bd4598a056b4bdcdd428ee`
- **npm package**: `opencode-ai@1.18.11`
- **platform package**: `opencode-windows-x64@1.18.11`
- **canonical installed binary**: `C:\Users\David\AppData\Local\hermes\node\node_modules\opencode-ai\bin\opencode.exe`
- **canonical SHA-256**: `578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35`

Artifact-provenance chain:

1. upstream source commit `012c2f57f976489d88bd4598a056b4bdcdd428ee`
   -> `RELEASE_TAG=v1.18.11` **PROVEN** (tag exists at that commit)
2. tag `v1.18.11` -> `npm opencode-ai@1.18.11` **SUPPORTED** (version field
   `1.18.11` in installed npm package metadata; platform package
   `opencode-windows-x64@1.18.11` is a sibling optional dependency in
   the same install)
3. `opencode-windows-x64@1.18.11` -> `installed opencode.exe` **PROVEN**
   (SHA-256 `578d7eb3...` matches the canonical installed binary; the
   sibling `opencode-windows-x64-baseline` payload is a different binary
   and was NOT substituted)
4. `installed opencode.exe` SHA `578d7eb3...` -> canonical binary **PROVEN**

**BINARIES**: installed binary is the AVX2-optimized release payload; the
separate `opencode-windows-x64-baseline` build is NOT used.

---

## INPUT

`RUN_INPUT_MECHANISM=POSITIONAL`

Source (`packages/opencode/src/cli/cmd/run.ts`, `resolveRunInput`):

```ts
function resolveRunInput(value?: string, piped?: string): string | undefined {
  if (!value) { return piped }
  if (!piped) { return value }
  return value + "\n" + piped
}
```

Invocation (`execute`, non-interactive branch):

```ts
const piped = process.stdin.isTTY ? undefined : await Bun.stdin.text()
message = resolveRunInput(message, piped) ?? ""
```

- `[message..]` is parsed as a single joined positional string (`args.message`).
- `process.stdin` is read **only** when `!process.stdin.isTTY` (piped/redirect
  input). It is NOT read in normal interactive terminal invocation.
- When both are present, the positional string is placed first and stdin text
  is appended after a `"\n"`. Both can coexist but positional is primary.
- Empty input (`message.trim().length === 0 && !args.command && !interactive`)
  causes the command to error and exit with code 1 — it does NOT silently
  read stdin in that case.
- For the governed non-live receiver, we require `message` positional text.
  stdin is an uncontrolled ambient channel for this adapter.

**Hermes choice**: `POSITIONAL` only. stdin is not a governed input channel.

---

## OUTPUT

`RUN_JSON_FRAMING=JSONL`

Source (`emit` function, same file):

```ts
function emit(type: string, data: Record<string, unknown>) {
  if (args.format === "json") {
    process.stdout.write(
      JSON.stringify({
        type,
        timestamp: Date.now(),
        sessionID,
        ...data,
      }) + EOL,
    )
    return true
  }
  return false
}
```

- Each event is a single JSON object followed by a newline (`EOL`).
- Stream is **JSONL** (one JSON object per line), NOT a single JSON document
  and NOT JSON-LD / NDJSON with multiple root values per line.
- `type` field is always present (e.g. `text`, `tool_use`, `step_start`,
  `step_finish`, `reasoning`, `error`).
- `timestamp: Date.now()` (ms since epoch).
- `sessionID` is present on every event.
- `data` is spread after those three fields; content depends on `type`.
- Stderr carries only CLI-level diagnostics/errors in human form; the
  structured JSON event stream goes to stdout exclusively.
- Terminal representation: `type: "text"` event carries the final assistant
  text in `data.text` (trimmed, non-empty). `type: "error"` carries
  `data.error`. There is no single "final document" envelope — the JSONL
  stream is the document.
- Ordering: events are emitted in subscription order (the `for await` over
  `events.stream`).

**Hermes choice**: JSONL parser: one `json.loads(...)` per line, skip blank
lines. `type`, `timestamp`, `sessionID`, plus `data`.

---

## PURE

`--pure` semantics (source: `packages/opencode/src/cli/cmd/run.ts`, permission
shared; `packages/opencode/src/plugin/index.ts`; `packages/core/src/v1/config/permission.ts`):

- `EXTERNAL_PLUGINS=YES` — `flags.pure` forces the internal plugin list to
  `[]` and overrides `cfg.plugin_origins` to `[]`, so no user/external
  plugins load.
- `PROJECT_PLUGINS=YES` — `flags.pure` forces `plugins = []`, which
  disables the project-origin plugin list.
- `USER_PLUGINS=YES` — implied by the plugin list being forced to `[]`;
  user plugins are part of the general plugin list.
- `MCP=YES` — `flags.pure` loads no MCP servers (no `mcpServers` injected
  and no user-configured MCP servers are loaded in pure mode).
- `CUSTOM_AGENTS=NO` — not explicitly disabled by `--pure`; agent
  selection via `--agent` still works.
- `HOOKS=YES` — plugins list is forced to `[]`, which includes hook
  adapters that come through the plugin system.
- `COMMANDS=YES` — not explicitly disabled by `--pure`; `--command` still
  works.
- `SKILLS=YES` — skills come through the plugin system, so they are
  disabled when the plugin list is forced to `[]`.
- `CONFIG_LOADING=NO` — user/project config still loads; `--pure` does
  NOT disable config loading.
- `BUILTIN_TOOLS=NO` — built-in tools remain available.
- `SHELL=NO` — shell/bash tools remain available.
- `FILESYSTEM_WRITE=NO` — `--pure` does NOT disable filesystem write tools.
  Write/edit/patch remain available.
- `NETWORK=NO` — `--pure` does NOT disable network access.

**Important**: `--pure` is a plugin/MCP/skill/hook disable, NOT a
filesystem/network/shell deny. It does NOT provide a security boundary on
its own.

---

## AUTO MODE

- `AUTO_DEFAULT=OFF` — absence of `--auto` leaves permission behavior at
  ask/deny (see below).
- `AUTO_EFFECT=auto-reply-once` — when `--auto` is present, each
  `permission.asked` event is auto-replied with `reply: "once"`. Without
  `--auto`, the loop auto-**rejects** the permission (the installed binary
  prints `permission requested: ...; auto-rejecting` and calls
  `client.permission.reply({ reply: "reject" })`).
- `QUALIFIED_CONTRACT_USES_AUTO=NO` — the governed adapter does NOT pass
  `--auto`.

---

## PERMISSIONS

OpenCode's permission model (source:
`packages/schema/src/v1/permission.ts`,
`packages/opencode/src/permission/index.ts`,
`packages/core/src/v1/config/permission.ts`):

- Values are `allow`, `deny`, `ask` (the `Action` literal schema).
- Default `evaluate()` return when no rule matches is `{ action: "ask",
  permission, pattern: "*" }` — i.e. **default is ask, not deny**.
- Rules are matched by `Wildcard.match(permission, rule.permission)` and
  `Wildcard.match(pattern, rule.pattern)`.
- Precedence: `findLast` wins — the last matching rule wins. Rules are
  merged across user/project/agent/tool configuration via `merge(...)`.
- `fromConfig()` expands permission objects like `{ edit: "deny",
  bash: "allow" }` into `{ permission: "edit", pattern: "*", action:
  "deny" }` etc.
- `disabled(tools, ruleset)` returns the set of tools whose `permission`
  is `deny` AND `pattern` is `"*"`. Tools in that set are hidden from
  the visible tools list (`visibleTools`).
- `edit`/`write`/`apply_patch` tools map to the `edit` permission.
- MCP tools map to the `read` permission family.

Concrete findings for the governed receiver:

- `FILESYSTEM_WRITE=DENIED` — `edit`/`write`/`apply_patch` are mapped to
  the `edit` permission. Default rule is `ask`; `--pure` does not convert
  to deny. The governed adapter must explicitly set the permission policy
  to deny edit/write/patch for the qualified contract. Source does NOT
  deny filesystem writes by default.
- `SHELL=NOT PROVEN` — shell/bash tools exist (config field `shell:
  Schema.optional(Schema.String)`). Their default permission action is
  governed by the same `ask`-default permission system, but the adapter
  cannot infer a deny from `--pure`. Denial must be set explicitly via
  the permission ruleset.
- `MCP=DENIED` — MCP servers are not loaded in `--pure` mode (MCP is
  part of the disabled plugin/system). The governed adapter treats MCP
  as `DENIED` under `--pure`.
- `TASK_NETWORK=NOT PROVEN` — network access is not explicitly disabled
  by `--pure` or by the permission defaults. The governed adapter must
  set network policy explicitly; source alone does NOT establish a deny.

---

## CONFIG (AMBIENT)

- `AMBIENT_CONFIG=ISOLATED` — config still loads, but the governed adapter
  MUST not rely on ambient user/project config. The receiver uses
  `OpenCodeTrustedConfig` (an explicit, frozen environment tuple +
  `working_directory` + pinned binary). No ambient config root override
  is used; the `config` field exists in the schema but the adapter does
  NOT pass an explicit config file path (the default config path is
  resolved from the working directory, so the working-directory choice
  is the isolation mechanism).
- User/global config: loads unless overridden by explicit config path.
- Project config: loads from the working directory unless overridden.
- Environment-derived config: the adapter controls `env` explicitly.
- MCP: not loaded in `--pure`.
- Plugins: not loaded in `--pure`.
- Agents: user-configured agents may still be loaded from config unless
  `--agent` is passed explicitly (the adapter passes `--agent`).
- Commands: not disabled by `--pure`.
- Skills: disabled in `--pure`.

Isolation mechanism: `--pure` + explicit `--agent` + explicit `working_directory`
+ controlled `env`. No `--config` override is passed; isolation relies on
`--pure` and the explicit config object.

---

## MODEL / AGENT SELECTION

- `MODEL_SELECTION_POLICY=pick(args.model)` — the `pick()` helper selects
  the model from `--model` if provided; otherwise falls back to the
  configured/default model. The governed adapter MUST pass `--model`
  explicitly; it must not delegate model selection to the message or to
  an untrusted caller.
- `AGENT_SELECTION_POLICY=pick(args.agent)` — `--agent` is passed
  explicitly by the adapter. Default agent comes from config otherwise.
- Precedence: explicit `--model` / `--agent` CLI flag wins over config
  default. The adapter's frozen `OpenCodeTrustedConfig` does not carry a
  model/agent default; the caller must provide them.

---

## CONTRACT ID

`OPENCODE_TRANSPORT_CONTRACT_ID` is recomputed below from the canonical
material (binary SHA + version + frozen transport choices).
