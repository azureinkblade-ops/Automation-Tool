# EA-4E.92N Read-Only SDK Compatibility Review

Baseline: 46c6e6780cb02e7a7910f2e34d45bc36375ad64b.
Result: SOURCE REVIEW COMPLETE / SDK COMPATIBILITY AND TARGET FREEZE HOLD.
Scope changed from acquisition qualification to prerequisite compatibility review
after discovering a potential conflict in the available local source. No new
acquisition implementation or qualification is claimed.

## Exact Read-Only Acquisition

The installed package metadata reports opencode-ai 1.18.11. Reading the installed
executable bytes reproduces the registered SHA-256 without running that executable.
The local source snapshot packages/opencode/package.json also reports 1.18.11.
The source directory has no Git repository metadata. Matching version strings
do not establish source-to-binary build provenance or effective SDK behavior.

Local base: C:\Users\David\AppData\Local\Hermes.

| Exact artifact beneath base | SHA-256 |
| --- | --- |
| node\node_modules\opencode-ai\bin\opencode.exe | 578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35 |
| node\node_modules\opencode-ai\package.json | de1da8f30650084a6261fe9a87a3126a63a6ea1365db2acdecb1cde640a86ee2 |
| opencode-1.18.11\packages\opencode\package.json | bf6340e9bbf727a2d945cd3212cfec46d71601834cf1d63085c2b553dbe4805c |
| opencode-1.18.11\packages\opencode\src\session\llm.ts | 5f1dcfb734853e39760e4dd05470f0c7d8752fc5dcc64e118c065149602e402d |
| opencode-1.18.11\packages\opencode\src\provider\provider.ts | 787bbb7ef3e61984d8c758c077f2d21bf6f847ec2cb4c37a159faf737babbaa1 |
| opencode-1.18.11\bun.lock | bce6162e5047110fc8bf36f62817aa57cb5642916e0fdf79a79c2a2e4427537e |

These are observed file hashes, not reviewed deployment-policy identities or
proof of receiver immutability. No raw runtime config or secrets are published.
No package downloaded, receiver invoked or endpoint contacted.

## Findings and Inference Limits

Local llm.ts imports streamText from ai at line 9 and invokes it at line 280.
The default AI SDK path uses fullStream; its middleware handles args.type ===
"stream". maxRetries at line 323 is input.retries ?? 0: the default is zero,
but this source expression alone does not prove retries are always forbidden.

provider.ts line 117 resolves @ai-sdk/openai-compatible through
createOpenAICompatible; lines 1694-1695 enable includeUsage unless disabled.
packages/opencode/package.json line 71 requests that package at 2.0.41;
bun.lock has the opencode-scoped resolution at line 6416. The lock contains
other scoped package versions, so the first global match is not sufficient.
These facts identify an inspection target, not the installed binary's resolved
package implementation or an observed HTTP body.

Inference: the available source's default AI SDK path may require streaming,
conflicting with frozen EA92I v1 provider.stream_allowed=false. This is a
compatibility risk requiring proof, not a definitive claim about executed
binary behavior. CLI stdout JSONL and provider HTTP streaming are different
interfaces; --format json does not establish non-streaming provider calls.

EA92M constructs a synthetic non-streaming body and cannot answer this question.
No new fixture should promote that synthetic body to actual SDK evidence.
No bounded search here proves global absence of package source or provenance.

## Required Resolution Before Target Freeze

1. Bind the actual effective SDK/package implementation to the pinned executable
   with trusted source/build or package evidence, rather than a version label.
2. Qualify the actual provider request construction against an inert fake transport
   in an isolated, reviewed harness with process/network tripwires. Importing an
   SDK must not execute receiver startup, plugins, package installation or network.
   Unknown side effects or unavailable exact implementation retain HOLD.
3. If a qualified path can make one non-streaming request, preserve v1 and prove
   exact effective model/body/route, no retry and no additional call.
4. If the actual path requires streaming, stop for a separately reviewed contract
   revision or compatible execution path. Do not strip stream=true, synthesize
   an SSE response, switch providers or silently relax the frozen admission rule.
5. Only after compatibility resolution continue trusted acquisition, policy owner
   binding, containment/CPU/cleanup qualification and full dependency closure.

## Safety and Checkpoint

One evidence file only; no production/test source change, binding roll or config
mutation. Current-ID test results, if run, are a separate identity regression
gate and do not qualify SDK behavior. EA92M raw inherited failures are unchanged
historical evidence; no broad rerun or full-green claim belongs to this review.

Existing test_ea4e67f_kilo762_successor.py and
test_ea4e67c_successor_candidate_contract_diff.py: 6 passed, 0 failed,
zero process/filesystem tripwire events. Interpreter is pinned stage2-v2 Python;
pytest uses no cacheprovider and fake-only/filesystem/report-host plugins with
fresh retained .pytest-ea4e92n-current-ids-a temporary directory.

No authority issuance, model/provider/receiver activity, listeners, downloads,
GPU/ComfyUI, file deletion or image-pipeline modification. Real target manifest
remains unfrozen. Production readiness HOLD; original live budget unconsumed.
