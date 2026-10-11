# EA-4E.92GT Interactive OpenCode Login Preflight

Status: NON-LIVE / READINESS HOLD. Parent: EA-4E.92GS. No receiver, model,
credential transfer, issuer, or production activation is authorized here.

## Decision and observed state

David selected his existing interactive OpenCode login as the preferred
account for a future governed OpenCode qualification. This is an account
preference, not proof of a credential usable by the isolated EA-4E receiver.
No credential value was read, copied, printed, or written in this preflight.

The committed receiver adapter sets a Hermes-specific effective home and
`OPENCODE_CONFIG_DIR`. The current isolated config selects
`ollama/qwen3:14b` at both top level and agent level, and defines only the
`ollama` provider. The isolated OpenCode state database exists, but its
mere presence does not establish an `opencode` Zen login or a usable token.
The interactive auth file exists; its top-level provider keys include
`openai`, not `opencode`. The previously observed interactive
`opencode/nemotron-3-ultra-free` selection is therefore not an attested
governed receiver selection. These observations do not establish whether
the user can sign in to Zen later or whether another credential store holds
relevant metadata.

OpenCode's current configuration documentation says a custom config file
is loaded between global and project config, and a custom config directory
is loaded after them. A custom directory is an override, not by itself a
proof of isolation. The installed OpenCode 1.18.11 source contract and
effective merged config must be requalified before a real capture. Source:
https://opencode.ai/docs/config/

OpenCode Zen lists `nemotron-3-ultra-free` at its chat-completions endpoint,
but says that model's NVIDIA free endpoint is trial-only and must not
receive personal or confidential data. It logs use for security and model
improvement. Until a separate data-use decision is made, this model is
limited to inert synthetic/public qualification content, not real agent
delegations containing source, credentials, private notes, or user data.
Source: https://opencode.ai/docs/zen/

## Required qualification before any live call

1. Choose and freeze the model and data class. A real confidential task
   requires a model/provider with separately reviewed data terms.
2. Prove an exact provider credential is available to the isolated receiver
   through an approved reference/broker. Do not copy the interactive auth
   file into the Hermes home or infer readiness from a file's existence.
3. Freeze the exact merged config, provider/model selection, endpoint,
   transport, egress policy, runtime identity, and one-call behavior for the
   installed binary. Rebind 92GS material without mutating older evidence.
4. Qualify a trusted issuer, credential/egress enforcement, process and
   model-invocation accounting, and a narrowly authorized live probe.

`EXISTING_LOGIN_SELECTED=YES` does not imply `CREDENTIAL_READY=YES`.
`PRODUCTION_READINESS=HOLD`. The separate exact mapped-byte and isolation
questions also remain open; this preflight does not close them.
