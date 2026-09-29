# EA-4E.92BL OpenCode Run Namespace

## Boundary

Non-live production-path correction from synchronized parent
`89342448501e40ad87a504a3b4fc6024eeaa3e0e`. No receiver, model,
provider/network, GPU, ComfyUI, production activation, or native parser
worker was invoked. Tests use injected fake process objects only.

## Defect And Correction

The adapter generated `runtime_run_id` for its invocation record but dropped
it when constructing `OpenCodeArgv`. `OpenCodeLiveProcess` consequently named
spool files from a short hash of executable and task argv, so distinct
authorized attempts with identical task argv could collide. The builder and
execution path now pass the bounded, safe runtime run ID through to the
process controller. Direct legacy argv objects without a run ID retain the
existing deterministic fallback.

Before process creation, the controller now creates an exclusive, fsynced
`<run_id>.claim` file. A second start of the same run ID is denied before
calling the process launcher, including across controller instances. A
failed or uncertain spawn leaves the claim in place; it is not automatically
refunded or deleted. This is a local namespace/duplicate-start guard, not a
durable authority ledger or proof that process creation occurred. The claim
file is not an authenticated capture manifest.

## Verification

- Process-free OpenCode adapter: 78 passed, 16 separately governed helper
  process cases deselected, zero process/filesystem guard events.
- OpenCode downstream plus fresh replay/fake-provider ladder: 351 passed,
  17 deselected (including the missing historical EA4 replay), zero guard
  events.
- Complete guarded Hermes Core: 4,575 passed / 35 raw inherited failures /
  six established OS-process tests deselected / 104 subtests passed. All 35
  failure identities exactly match EA92BK. Fake-only process guard denied
  32 helper starts; filesystem guard events were zero. Raw suite is not
  green. JUnit `.pytest-ea4e92bl-full-a/result.xml`, SHA-256
  `251c231589b7c5dcc0d94cd1edbed33173b56b89f2f5475271916346845ae9a6`.

## Remaining Hold

No real OpenCode capture was started. The capture-only authority/process
owner, independent provider-call observation and egress containment,
CPU-only model proof or separate GPU authority, trusted capture manifest,
exact one-shot live authorization, and cleanup observation remain OPEN.
EA92S exact mapped-byte invariant remains REJECT/HOLD. This checkpoint
does not establish production readiness.
