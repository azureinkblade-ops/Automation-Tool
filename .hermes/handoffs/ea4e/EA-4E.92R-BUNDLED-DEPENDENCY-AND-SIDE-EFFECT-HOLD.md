# EA-4E.92R Bundled Dependency and Side-Effect Review

Baseline: a8e0c049d9994ba912fd53cfe53131f1b7ee6553.
Result: CANDIDATE DEPENDENCY DISCOVERY / IMPORT SAFETY HOLD.
Evidence-only static review. No SDK module imported or executed.

## Bounded Method

Search the pinned binary for exact NUL-delimited Bun module paths. Inspect
read-only 65536-byte windows beginning at observed path offsets. Require two
delimiters and // @bun preamble before computing exact region hash. Retain
metadata only; no extracted module files written. Candidate literal import
references are lexical matches, not JavaScript AST or semantic acceptance.

Full pinned binary hash rechecked unchanged:
578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35.
Path: C:\Users\David\AppData\Local\Hermes\node\node_modules\opencode-ai\bin\opencode.exe.
Observed consistency is not enforced file immutability or trusted runtime admission.

## Findings

EA92Q's three from-clause dependencies remain candidate references. Reviewing
chunk-aaw76hgx.js discovers chunk-bb9rdmbz.js transitively, proving the earlier
three-reference list was not a complete dependency closure.

| Module | Code start | Code length | Exact region SHA-256 |
| --- | --- | --- | --- |
| chunk-aaw76hgx.js | 107502388 | 35101 | 7d334281225a165b802f450233435301bcdb8ccb597dad390d22cf7acdc3bbb2 |
| chunk-68v9qbwq.js | 107537521 | 5621 | 83363d6e445efe06be2b16b66089954694fc0bb892cb62707e63f2438b497c33 |

All module paths are beneath the observed B:/~BUN/root virtual path, not host
filesystem paths to import. aaw76hgx has literal references to 68v9qbwq,
bb9rdmbz and sm6trb15. 68v9qbwq had no candidates under this lexical pattern;
that does not prove absence of dynamic imports, require or other capabilities.

sm6trb15 module-path offset is 107546921. Its next delimiter was not found in
the 65536-byte window. The review raised Module boundary missing, returned no
module hash and did not classify or execute that dependency. Do not truncate
the module and call it qualified, invent a hash, or silently widen the bound.
bb9rdmbz remains pending transitive inspection.

The inspected prefix of aaw76hgx includes asynchronous utilities with timers
inside functions. 68v9qbwq includes error classes and Symbol.for initializations.
These observations are not a complete top-level side-effect review or proof of
safe import. Dead code, initialization, dynamic loaders and hooks require proper
syntax/dataflow inspection before an inert harness may execute anything.

## Parser and Harness Boundary

No usable parser was found at the three specifically checked package paths:
Automation tool/node_modules/acorn/package.json,
Automation tool/node_modules/@babel/parser/package.json, and
Hermes/node/node_modules/@babel/parser/package.json.
This is a bounded path observation, not global absence. A subsequent attempted
recursive parser filename regex failed to compile and supplies no absence proof.
No parser installed or downloaded; no SDK startup used as a parser surrogate.

Next safe slice is a reviewed static-analysis contract: exact parser artifact
identity and acquisition, isolated parser runtime, maximum module/aggregate bounds,
strict extraction/path validation, AST import/export graph, dynamic-reference
classification and top-level initialization review. Exceeding any bound or
unresolved dependency keeps HOLD. Parser execution must not resolve/evaluate SDK
imports, install packages, start plugins or make network/process/model calls.

Only after complete qualified dependency closure and effective config/hook
selection review may a separately authorized inert SDK harness execute the
extracted implementation. Fixture mocks must not be substituted for actual
dependency behavior and advertised as SDK proof. Frozen v1 remains unchanged;
any required streaming compatibility revision needs separate design acceptance.

## Checkpoint and Safety

One evidence file. Formatting and exact staged scope are the checkpoint gate;
no new production/test source, new regression result or full-suite rerun claimed.
EA92Q's six current-ID passes remain historical for its exact source checkpoint.

No receiver/model/provider calls, SDK imports, parser execution, runtime/config
mutation, deployment/activation/issuance, listener, download, GPU/ComfyUI or deletion.
Historical authority and Kilo pins unchanged. Candidate discovery is NOT source
closure PASS, import-safety qualification or production readiness. Target freeze,
effective request compatibility and import safety remain HOLD.
