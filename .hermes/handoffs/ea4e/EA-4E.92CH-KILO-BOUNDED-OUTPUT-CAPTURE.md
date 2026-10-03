# EA-4E.92CH Kilo Bounded Output Capture

## Scope

Non-live hardening of the Kilo process controller at the synchronized
7.8.3 source baseline `891083baa1eff9c148c29d1f3d85d34f9126acc1`.
The prior `communicate()` path buffered stdout and stderr without an
incremental byte limit. This change replaces it with two concurrent,
bounded pipe readers. It does not change argv, model selection, receiver
identity, authority issuance, activation, registry, or sealed ID material.

## Behavior

- Stdout retains at most 4 MiB; stderr retains at most 128 KiB.
- The first byte beyond either cap causes the owned child to be killed.
  The terminal result has return code `-1` and `output_overflowed=True`.
- A terminal `poll()` cannot report a successful exit after overflow.
- Timeout still kills and reaps the child and sets `timed_out=True`.
- Captures start when the handle is constructed, so output cannot grow in
  Python memory while an async caller waits before `wait()`.
- A reader that does not finish after the child exits fails closed with
  `KiloProcessError` instead of returning truncated output as success.

The byte cap applies to captured pipe content, not a provider token budget
or the number of model calls inside Kilo. The metadata-only 92CC probe is
separate and its output check is still post-process. The canonical Kilo
transport material does not include an output-cap field; these limits are
implementation hardening, not a claimed sealed contract revision. If a
future authorization relies on them as a cryptographic invariant, that
requires a reviewed contract roll.

## Qualification

- Focused fake-only successor gate: **255 passed, 0 failed**, with zero
  process/socket tripwire events.
- Inert Windows host check using Python as the child, not Kilo: normal
  output, stdout overflow, stderr overflow, and timeout: **1 passed**.
- Complete Hermes Core fake-only run before adding the opt-in host test:
  **4,683 passed, 56 failed, 104 subtests passed**. The 56 failure
  identities exactly match the prior committed candidate report; new
  failing identities: **0**. The full suite remains red.
- The host check is opt-in via `EA4E_RUN_INERT_KILO_CAPTURE=1`; by default
  it skips, so the fake-only suite never spawns its Python child.

No Kilo receiver, model, provider, network, GPU, or ComfyUI call occurred.
No production activation was enabled.

## Remaining boundary

The source change needs staged and committed-tree verification before a
checkpoint can be accepted. A real Kilo 7.8.3 task still requires separate
exact one-shot authorization and accounting. The 56 inherited failures
remain visible. The EA-4E.92S exact mapped-byte proof HOLD is unaffected.
