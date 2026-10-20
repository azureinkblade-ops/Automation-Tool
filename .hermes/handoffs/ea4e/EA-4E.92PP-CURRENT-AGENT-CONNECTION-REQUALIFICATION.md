# EA-4E.92PP Current Agent Connection Requalification

Status: NON-LIVE PASS / LIVE RECEIVER HOLD. Source baseline:
`192a6e9abf2bcb051a19fbff34bc0c9982f8edb3`.

## Current local identity

Read-only SHA-256 observations, without executing either receiver:

| Material | Observed SHA-256 | Source pin |
| --- | --- | --- |
| Kilo 7.8.3 executable | `8b042a53c3d3e5e2043f37392c3d62e7d5c278dc7740d93aeb6fa91df7ccc63a` | Match |
| OpenCode 1.18.11 executable | `578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35` | Match |
| Isolated OpenCode `config/config.json` | `bf98deaa2a8c052213a599716c5fa2d229bb89b72d7cb810e7b6a4cc178b7756` | Same as 92BE observation |
| Isolated OpenCode effective-home permission config | `98e31c27edb2aceb91a310a742e25d188cc50ca840fea056cc169fe50e88a649` | Observation only |

No credential or configuration contents were copied to this evidence.

## Requalification

At this source commit, seven shared-store agent text-result, originator-return,
Codex question, and recovery test modules passed **58/58**. Five fake
capture/provider accounting and offline replay modules passed **108/108**.
Both invocations used the pinned stage2-v2 interpreter, fresh basetemps, and
made no receiver or model invocation. These are targeted results, not a full
Hermes Core regression claim.

The fake chain demonstrates a software communication model among Hermes,
Codex, Kilo, and OpenCode. It does not show a model-authored response. The
existing `opencode_capture_entry.py` is default-disabled, injected-port and
fake-origin only; its provider boundary cannot contain a receiver that
bypasses the injected port. The historical missing OpenCode capture remains
missing. Current binary hash agreement does not qualify live receiver behavior.

## Decision and next boundary

`CURRENT_FAKE_CONNECTION=PASS`

`CURRENT_KILO_AND_OPENCODE_BINARY_PIN=PASS`

`CURRENT_LIVE_RECEIVER_QUALIFICATION=HOLD`

`PRODUCTION_READINESS=HOLD`

The next substantive gate is an independently governed capture-only **real**
receiver path with a trusted one-shot issuer, OS-level provider egress and
call accounting, durable raw stream/cleanup evidence, and an exact bounded
live authorization binding source, executable/config/model, task bytes, call
budget, and deadline. Current generic continuation approval does not supply
that packet. The accepted 92DE local-container trust profile is distinct from
the strict 92AT mapped-byte REJECT/HOLD. No issuer was installed, no native
installer or Docker mutation was run, and no receiver, model, GPU, ComfyUI,
or production activation was invoked in this checkpoint.
