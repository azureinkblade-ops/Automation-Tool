# EA-4E.92BS Non-Live OpenCode SDK Compatibility

Baseline: `6517efdfcd7b9431201e87b9a8fda4a68971743a`.
Scope: pinned SDK package behavior only. This is not an OpenCode receiver run,
an installed-binary attestation, a model/provider call, or live authority.

## Exact package selection

The local OpenCode 1.18.11 `bun.lock` resolves the opencode-scoped
`@ai-sdk/openai-compatible` package to 2.0.41 and `ai` to 6.0.168. An isolated
temporary npm installation used those exact versions, their pinned provider
3.0.8, provider-utils 4.0.23, zod 4.1.8, eventsource-parser 3.1.0, and
standard-schema/spec 1.1.0. Package-lock SHA-256:
`6b5a7827b936fa8bdb09e73d5ca848e53b5bccd8036c3e416ff8ffc3d04c7491`.
The test verifies versions and SHA-512 integrity strings against the scoped
lockfile entries before importing the SDK. npm acquisition used the package
registry during setup with lifecycle scripts disabled. The subsequent SDK
behavior test made no real network call. The retained installation is under
`%TEMP%\ea4e92bs-sdk-compat`, outside the source tree and app runtime.

Local source snapshots: `session/llm.ts` SHA-256
`5f1dcfb734853e39760e4dd05470f0c7d8752fc5dcc64e118c065149602e402d`;
`session/prompt.ts` SHA-256
`79519fc90f6cac8ee992a7d772474e257758bcff44a2fe3b402bb1803ef72c3e`.
The former calls `streamText()` on its default AI SDK path. The latter has a
title-generation path passing `retries: 2`. These source facts are not proof
that the installed binary executes precisely these bytes or that a particular
capture task invokes title generation.

## Inert test and result

`tests/hermes_core/test_ea4e92bs_sdk_compat.cjs` injects an in-memory fetch
into `createOpenAICompatible()` and replaces global fetch, common socket
functions, and child-process entrypoints with throwing tripwires before
loading the SDK. It uses a loopback-shaped URL but starts no listener and
sends no packet. All responses are synthetic. Test output:

```json
{"sdkOnly":true,"realReceiverStarted":false,"realNetworkCalls":0,"streamText":{"requests":1,"stream":true},"streamFailure503":{"requests":1,"retried":false},"streamFailure503WithTwoRetries":{"requests":3,"retried":true},"generateText":{"requests":1,"stream":false}}
```

With one simple prompt and `maxRetries: 0`, SDK `streamText()` sends one
`POST /v1/chat/completions` with `stream: true`. A synthetic 503 is not retried
under that setting. With `maxRetries: 2`, the same synthetic 503 produces
three attempts. `generateText()` sends one non-streaming request for the same
simple prompt. This does not establish how many calls a whole OpenCode session
makes, whether it runs title generation, or whether its installed binary uses
this precise package build. The frozen provider binding still requires
`stream_allowed=false` and a one-call limit, while its offline HTTP handler
rejects streaming. Do not silently reinterpret that v1 contract as accepting
SSE or conflate one receiver process with one provider call.

Focused fake-only Python gate: 178 passed, zero fake-only process events and
zero filesystem tripwire events across provider binding, admission, offline
HTTP, and fake binding-composition tests. Node SDK test passed after the
transitive parser was corrected from npm's initially selected 3.1.1 to the
lockfile's 3.1.0. No broad-suite or installed-binary qualification is claimed.

## Disposition

`SDK_PACKAGE_BEHAVIOR=QUALIFIED_INERT`,
`DEFAULT_SOURCE_PATH_NONSTREAMING_V1_COMPATIBILITY=FAIL_CONDITIONAL_ON_SOURCE_BINDING`,
`INSTALLED_BINARY_EFFECTIVE_REQUEST=UNPROVEN`,
`ONE_CALL_FOR_WHOLE_SESSION=UNPROVEN`, `PRODUCTION_READINESS=HOLD`.

Next: review a distinct streaming-capable contract or an independently
qualified non-streaming execution path; explicitly address the title-path
retry and any other internal LLM calls. Then bind source/package behavior to
the installed executable with a separately authorized one-start inert
receiver probe or trusted build provenance. EA92S exact mapped-byte proof,
trusted capture issuer, bypass containment, and CPU policy remain separate
unclosed gates. No live receiver, model, provider, GPU/ComfyUI, or production
activation is authorized by this checkpoint.
