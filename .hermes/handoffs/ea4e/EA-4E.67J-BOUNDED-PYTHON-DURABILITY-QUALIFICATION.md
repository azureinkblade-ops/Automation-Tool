# EA-4E.67J Bounded Python Durability Qualification

Baseline: 37e3529297ff2efe7ee2ca6f70c46fbbab5b028f.

Candidate-only evidence; not yet committed or committed-tree qualified.
The EA-4E.67I strict-fake HOLD remains historical. This run separates real
Python durability helpers from fake-only qualification, without changing the
existing fake-only guard.

## Observed results

- Four explicitly selected durability OS-process tests: 4 passed, 0 failed.
- Exactly 9 Python helper launches, 0 guard denials; all helpers exited.
- Separate restart/durability/concurrency fake-only ladder: 202 passed,
  4 real-process tests deselected, 0 tripwire events.
- Guard rejection tests: 4 passed, 0 process launches, 0 outer tripwire events.
  Rejected wrong executable, wrong mode, out-of-root storage, and shell option.

## Boundary

Only the current Python executable and inspected durability helper are allowed.
Their hashes are checked for changes relative to qualification startup, not
represented as a durable frozen identity. Exactly four test nodes are admitted.
Only claim/precommit-crash modes and isolated temporary state are admitted.
Maximum nine launches; credential environment is not inherited. The helper
installs an audit hook denying nested subprocess and socket capabilities before
importing production store code. Parent network/shell tripwires remain active.
Unfinished children are killed and reaped at session finish and fail the run.
This is Python-level containment, not a universal OS sandbox.

## Evidence limits

The historical postcommit-crash test performs a normal successful claim and
process exit. It proves durable consumption, not an abrupt postcommit/preanchor
crash. No stronger crash claim is made. The simultaneous four-process test
accepts ERROR for losing claims; passing it is not proof all losing claims DENY.
No real receiver/model task, authorization issuance, activation, GPU or ComfyUI
operation occurred. No commit or push performed in this slice.

## Next qualification

Freeze exact helper/interpreter identities; extend denial and budget/cleanup
tests; tighten simultaneous-claim loser assertions; qualify an actual abrupt
postcommit/preanchor crash separately. Complete successor source-closure review
and clean committed-tree regression before checkpointing successor rollout.
