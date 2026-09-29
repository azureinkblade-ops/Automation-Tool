# EA-4E.92BF Receiver Result Fail-Closed Qualification

## Boundary

Non-live correction on `feature/ea4e67-kilo762-roll` from synchronized parent
`1ed3026d64fa8874496a01a5b565055c39d24035`. No receiver, model,
provider endpoint, GPU, ComfyUI, or production activation was invoked.

## Defect And Correction

Both Kilo and OpenCode JSONL parsers selected text before a later error event.
A text-plus-error stream could therefore be marked as a verified success.
Kilo also accepted text from a nonzero exit or timed-out process, and recorded
some invalid results as completed. OpenCode dropped a fake/process result's
`timed_out` flag while reconstructing its process result.

Both parsers now give any error event precedence over text. Kilo verifies only
text from a zero-exit, non-timeout process and records other outcomes as error.
OpenCode preserves timeout state and verifies only text without timeout or
cancellation. Focused fake tests cover error-only and text-then-error streams,
exit failure, and timeout; the preexisting OpenCode timeout expectation was
corrected to require invalid verification.

## Verification

Pinned interpreter: `.venv-stage2-v2/Scripts/python.exe`. All tests used the
fake-only process guard, filesystem guard, and non-live report host plugins.

- Initial new tests reproduced nine failures before the production correction.
- Adapter files, excluding the 15 separately governed Python-helper process
  cases: 183 passed, 15 deselected; both guard event counts zero.
- Downstream Kilo/OpenCode governed and production qualification: 238 passed;
  both guard event counts zero.
- Final affected adapter and binding selection after the terminal-state change:
  234 passed, 15 deselected; both guard event counts zero.
- Canonical full fake-only Hermes Core after the final code change: 4,511
  passed, 35 raw inherited failures, six established OS-process tests
  deselected, 104 subtests passed. The fake-only guard denied 32 attempted
  subprocess launches; filesystem guard events were zero. The raw suite is
  not green. Its 35 failure identities exactly match the prior canonical run
  in `.pytest-ea4e92bf-full-b/result.xml`, with zero added or missing.
  Final report: `.pytest-ea4e92bf-full-c/result.xml`, SHA-256
  `2481282b7b1b9b261c8e94cb5056271a9c03d2cbabf15c1c158e3bee597775e1`.

An initial full command excluded two wrapper tests instead of the documented
process-spawning tests and produced 37 raw failures. It was corrected to the
established six exclusions; this is not treated as an application regression.

## Remaining Boundary

This fixes false-success classification in the adapters; it does not qualify a
current live Kilo or OpenCode call. The missing historical OpenCode JSONL
capture, separately governed process tests, current receiver/model authority,
and EA92S exact image-byte HOLD remain open. Do not infer production readiness
from fake-only passing tests.
