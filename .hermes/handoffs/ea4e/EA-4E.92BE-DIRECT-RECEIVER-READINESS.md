# EA-4E.92BE Direct Receiver Readiness Check

## Boundary

Non-live, read-only host inspection and guarded tests at parent commit
`38f6804444045b9dde72528ee4ed7b476fb219d5`. This is a direct
Kilo/OpenCode connection check, not an EA92S parser-worker qualification.
No receiver, model, provider endpoint, GPU, ComfyUI, or production activation
was invoked. Executables were hashed, not run. No config values that may
contain credentials are retained here.

## Current Receiver Identities

| Receiver | Local binary | SHA-256 result | Scope of result |
| --- | --- | --- | --- |
| Kilo | 7.7.9 executable at the EA92AJ path | `9ef2ca9633cece72293d269502bee16720d9179990c1b65abc0599c6d356bd07` | Matches EA92AJ's non-live successor pin; does not requalify a live task. |
| OpenCode | 1.18.11 executable at the adapter's pinned path | `578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35` | Matches the current adapter pin; does not prove live provider behavior. |

The isolated OpenCode `config/config.json` exists. Its observed SHA-256 is
`bf98deaa2a8c052213a599716c5fa2d229bb89b72d7cb810e7b6a4cc178b7756`.
Its top-level keys include `provider`, `model`, and `agent`; the global and
named-agent model selection both identify `ollama/qwen3:14b`. The separate
effective-home `.opencode/config.json` is a permission-policy document; it
is not evidence that the production binding/policy artifacts are frozen.
The provider options inspected have a `baseURL` field but no observed
CPU/device policy field. This bounded observation does not prove the model
would or would not use GPU.

## Guarded Test Results

Interpreter: `C:\Users\David\Documents\Automation tool\.venv-stage2-v2\Scripts\python.exe`.
Both runs used `-p no:cacheprovider` and the established
`tools.ea4e67_fake_only_guard`, `tools.ea4e67m_filesystem_guard`, and
`tools.ea4e67n_nonlive_report_host` plugins with fresh retained basetemps.

- Initial six-file receiver/binding selection: **319 passed, 16 failed**.
  Fifteen OpenCode adapter cases require Python helper subprocesses and were
  deliberately denied by the blanket fake-only guard (15 denied attempts).
  The remaining failure is the existing missing historical capture
  `run-d1eca109.stdout.jsonl`. These are raw failures, not a green suite.
- Process-free five-file selection, excluding only that historical replay
  case and the helper-process test file: **252 passed, 1 deselected**.
  Fake-only process and filesystem tripwire events were both zero.

The 15 helper-process cases require their separately qualified bounded
process envelope; this checkpoint did not run or relabel them. The missing
historical capture remains missing, not an expected failure or reconstructed
artifact. No full regression gate was run.

## Connection State and Next Gates

1. **Kilo:** EA4E9 contains historical one-shot live evidence at an older
   source/binding. EA92AJ pins the currently installed 7.7.9 successor
   non-live. Current-binary hash agreement and fake tests are not a current
   live behavioral proof or production activation. A new real task needs an
   exact receiver, model, source, authority, process, and cleanup envelope.
2. **OpenCode CLI:** The direct CLI adapter and parser exist, and the
   installed binary/config are observable. EA91's original raw capture is
   absent. EA92A permits a **fresh, separately classified** one-shot capture
   to satisfy prospective replay only; it cannot repair EA4 history. That
   live call requires separate exact authority and accounting. The current
   config alone does not establish CPU-only execution or complete effective
   provider behavior.
3. **OpenCode provider deployment:** EA92I-M qualify schema and fake
   composition, but EA92N records unresolved actual SDK streaming behavior;
   EA92L's target policy artifacts and trusted owners are unfrozen. No real
   OpenCode provider binding or 13 shared downstream IDs may be rolled from
   fixture data. The EA92S contained parser worker is one proposed static
   inspection mechanism, not the Kilo connection and not the OpenCode CLI
   replay transport itself; its exact 92AT image-byte requirement remains
   on HOLD under the user's 92BB decision.

No change to production routing, authority, registry, activation, provider
configuration, model binding, or tests follows from this check. The next
execution-capable step must be an exact bounded live-authorization decision,
not inferred from this evidence or a generic continuation request.

`KILO_BINARY_PIN_MATCH=YES`

`OPENCODE_BINARY_PIN_MATCH=YES`

`DIRECT_CONNECTION_PROCESS_FREE_GATE=252_PASS_1_DESELECTED`

`HISTORICAL_OPENCODE_CAPTURE=STILL_MISSING`

`CURRENT_LIVE_RECEIVER_QUALIFICATION=NOT_PERFORMED`

`PRODUCTION_READINESS=HOLD`
