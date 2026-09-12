# EA-4E.67G Corrected Candidate and Concurrency Hold

Result: CORRECTED CANDIDATE GATE PASS / BROADER QUALIFICATION HOLD.
Branch: feature/ea4e67-kilo762-roll.
Source baseline before this evidence-only checkpoint:
`0c0d322acc92163d0693c64ee987bf63b48cf162`.

## Candidate Model Correction

Uncommitted candidate test now reconstructs the historical 7.5.16 chain and
asserts all 13 IDs equal preserved historical constants, then propagates new
17/21/22 cache values to importing modules as well as the defining module.
It asserts imported-cache coherence before and after the transition.
A separate regression test proves a stale imported cache changes invocation ID.

Corrected four candidate values:

- 23: `6191b758a61848b27068bf8d18b44b91cb0b32eb3e391a58a5ccd3c1908ef9a9`
- 26: `9e3118549e6e26e574b93b81aefd816228722d5feb525cad8a10086ad62a86e0`
- 28: `c6859afb31ffb218cfb09e8f4e6a7f355165bb47fa386d603f0689506ae38d58`
- 29: `11a5230334804d82405994a8ccaa62c0a4a49c2cd01a34854ab75758ba090525`

These observed candidate values replace the four flawed prototype predictions
for further qualification, not historical records. They are not yet an accepted
committed production reseal. The other nine observed candidate IDs are unchanged.

Candidate correction + successor + adapter + Kilo qualification gate:
**138 passed / 0 failed / 0 tripwire events**.
This result is from uncommitted WIP, not an exported committed successor tree.

## Broader Failure and Baseline Comparison

The 11-file predecessor ladder comprises receiver router/dispatch, production
dispatch/activation/execution/issuance, governed production, executor binding,
invocation authorization/issuer, and governed caller tests.

- Candidate ladder run 1: 359 passed / 1 failed / 0 events.
- Concurrent double-use test isolation: 1 passed / 0 failed / 0 events.
- Candidate complete ladder rerun: 359 passed / 1 failed / 0 events.
- Committed-baseline export ladder, two runs: each 355 passed / 5 failed / 0 events;
  those five failures require the removed 7.5.16 binary in activation tests.
  The concurrency failure did not reproduce in those two baseline runs.
- Complete invocation test file, baseline export: 38 passed / 0 failed / 0 events.
- Complete invocation test file, candidate: 38 passed / 0 failed / 0 events.

Candidate ladder failure:
`test_production_invocation_authorization.py::test_concurrent_double_use_excluded`.
Exactly one permit was allowed and one denied, but denial was
INVOCATION_AUTHORIZATION_STATE_INVALID instead of
INVOCATION_AUTHORIZATION_ALREADY_CONSUMED. At-most-one execution passed;
the integrity-state/denial contract did not.

No demonstrated exoneration: the same signature was not reproduced on these
baseline runs, and an isolated pass is insufficient to normalize the repeated
candidate ladder failure. No zero-new-failures or full-green claim is made.

## Likely Race Window Requiring Proof

DurableInvocationAuthorizationStore.claim commits the advanced database
generation, invokes _after_database_commit_before_anchor, then publishes the
external anchor. A concurrent caller can acquire BEGIN IMMEDIATE after the
commit and verify database generation before anchor publication. An integrity
exception is mapped by the invocation policy to STATE_INVALID.

This is a source-grounded hypothesis, not a deterministic reproduction or proof
of stored corruption. Required next: barrier-controlled reproduction using the
existing post-commit/pre-anchor test hook, followed by a synchronization design
covering threads and independently opened store instances without weakening
rollback detection, fail-closed crash handling, or at-most-one consumption.
Do not simply accept STATE_INVALID in the contention assertion.

## Git / Runtime Boundary

Only this HOLD evidence is eligible for the evidence-only checkpoint.
Production rollout and test corrections remain uncommitted and unstaged in the
isolated worktree. Existing source and test changes are not qualified for push.
No merge into the live integration branch, deployment, binding renewal,
authorization issuance, receiver/model task, GPU generation, or ComfyUI work.
