# EA-4E.92Q Bundled SDK Byte Lineage Review

Baseline: 283b9cb9161d2fce5c68cc223c63def357eb0d4e.
Result: BUNDLED MODULE BYTE LINEAGE ESTABLISHED / EFFECTIVE REQUEST PATH HOLD.
Evidence-only static review, no new production/test source or SDK execution.

## Objective and Scope Correction

EA92O lacked unpacked SDK evidence. EA92P found package and streaming markers
inside the pinned executable but did not identify the owning module. This review
follows compiled loader/export aliases and a bounded NUL-delimited byte region.
It establishes an embedded implementation's byte identity without assuming the
loose source snapshot produced the binary. It does not establish upstream signed
build provenance, complete runtime module closure or actual effective SDK calls.

Pinned executable:
C:\Users\David\AppData\Local\Hermes\node\node_modules\opencode-ai\bin\opencode.exe.
Full binary SHA-256 remains:
578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35.

## Exact Static Mapping

1. Provider loader window at 102161300, length 2048, maps
   @ai-sdk/openai-compatible to B:/~BUN/root/chunk-13nqztj7.js and resolves
   createOpenAICompatible.
2. Wrapper window at 120933491, length 2048, imports qi/ri/si/ti/ui/vi from
   chunk-ja2qge1j.js. It exports qi as OpenAICompatibleChatLanguageModel,
   ui as VERSION and vi as createOpenAICompatible.
3. Implementation export window at 99335000, length 2048, maps bG -> qi,
   dG -> ui and jQ -> vi.
4. Factory window at 99333200, length 2048, contains dG="2.0.41" and
   function jQ. The factory constructs bG for chat and languageModel delegates
   to that chat constructor. This identifies an embedded version-labelled
   implementation, not authenticated upstream package metadata.
5. bG=class occurs at 99314594 inside the bounded implementation region.
   Its doStream constructs stream:true before transformRequestBody and invokes
   /chat/completions with streaming response handling. Transformation/fetch hooks
   can affect the eventual request; raw effective wire bytes remain unobserved.

The first package window at 100493817 belongs to native adapter selection, not
the above factory. Other package-string matches represent unrelated providers.
Marker adjacency/first match is not a substitute for following aliases.

## Byte Region and Receipt

A read-only 65536-byte window begins at module-path offset 99309493. The exact
NUL-delimited path equals B:/~BUN/root/chunk-ja2qge1j.js. Its next NUL-delimited
region starts with // @bun. Observed code start: 99309524; length: 25767 bytes.
SHA-256 of exact region:
0aeee20b39a92924e486c68002082b33a7b0ff9ad0b09b34e87e668d55f79f83.

Seven fixed token checks passed: bG=class, async doStream, stream:!0,
var dG="2.0.41", function jQ, new bG, export{bG as qi.
Read failures, short windows, absent delimiters/path/preamble or missing tokens
raise errors; no embedded code was imported, evaluated or written to disk.
This bounded discovery is not a general PE/Bun container parser. It follows an
observed plain-text region; token checks are not a JavaScript semantic proof.

From-clause inspection found imports of chunk-aaw76hgx.js,
chunk-68v9qbwq.js and chunk-sm6trb15.js. It is not an authoritative import closure
or side-effect safety analysis. All dependencies must be qualified before an
inert harness may import or execute even this embedded provider implementation.

## Bounded Window Hashes

| Offset | Length | SHA-256 |
| --- | --- | --- |
| 100493817 | 1536 | 8a8992774757f98bee7288ecc41d01a0e362d95b7b8d90dc14506d81844525ff |
| 102161300 | 2048 | 3d6af6657beb563215c87a814a9c04f379a3ecfdc83d15f9ce05c6f10c6540bb |
| 120933491 | 2048 | fdb15015923968434a3af197ed59a8e39882c4dde986647363befbace9166a17 |
| 99335000 | 2048 | 19939035bdd653a7e0c654c439a12ab734c20363c04ddcaf8297fdbe3a0a2e74 |
| 99333200 | 2048 | 45c81ceccc6eba3eb1dbec9ee0764f5bcc1bb48a028e89c638cfb2e87f15246f |
| 99317300 | 2048 | ac412aa89e612ec4bfcaee12f8ad8baf9e17203bd5f6802e4dfe9fbdfda7028f |
| 100591400 | 2048 | 53cde494f9451e99ce6583a0a125b0074d0742cae351cf4ad7c468ed72aeb522 |
| 106421800 | 2048 | 640b12c9a411b7b36f4a480a8dd9de443b35564d0271a7fe527b5a54c15271e2 |

Runtime-selection window 100591400 shows native opt-in/fallback to AI SDK,
stream middleware and maxRetries supplied or default zero. Generic compatible
provider hook window 106421800 loads the same wrapper, with includeUsage enabled
unless explicitly disabled and an existing-sdk early exit. Configuration/hook
selection and fetch/body transformations remain possible runtime seams; no
effective selected request has been captured or admitted.

## Verification and Governance

Observed binary hash rechecked after static reads; unchanged. This is observed
consistency, not enforced immutability or trusted acquisition admission.
Existing current-ID tests: 6 passed, zero failures and process/filesystem events,
pinned stage2-v2 Python with fake-only/filesystem/report-host plugins and fresh
.pytest-ea4e92q-current-ids-a state. No new regression or full-suite run is claimed
for this evidence-only step. EA92P's full committed raw gate remains historical.

Next: review exact bundled dependency/side-effect closure and effective provider
configuration/hook routing before authorizing a strictly inert extracted SDK
harness. Do not patch imports or fake their behavior and call it actual SDK proof.
If compatibility requires streaming, a separate bounded streaming-contract design
or qualified compatible path is needed; frozen v1 remains unchanged.

No runtime/credential/config changes, policy deployment, source/registry roll,
activation/issuance, receiver/provider/model calls, listeners, SDK execution,
downloads, GPU/ComfyUI or deletion. Kilo runtime pins/historical authority unchanged.
Real target freeze and production readiness HOLD; live budget unconsumed.
