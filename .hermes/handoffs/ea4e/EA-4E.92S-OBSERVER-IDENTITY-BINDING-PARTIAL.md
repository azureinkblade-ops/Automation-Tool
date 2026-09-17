# EA-4E.92S Observer Identity Binding Partial

## Finding

The committed probe start schema stores integer job/process/thread values. A
Windows job handle is process-local, so its integer value cannot identify the
same job from a separate post-crash observer. Process and thread IDs alone are
also insufficient durable identities because the operating system may reuse
them. A concrete native snapshot provider built directly on the current three
integers could observe an unrelated resource and falsely report cleanup.

## Decision

NQ-12 will use a separately owned watcher established before broker launch.
The watcher retains the exact job/process/thread handles. Durable evidence
stores only distinct opaque SHA256 token identities for those retained handles,
the watcher instance UUID, PID/TID, process/thread creation times and the
monotonic binding time. Raw native handle values are never serialized as
cross-process identities.

The watcher must fail closed after watcher-instance loss or token-registry loss.
It must compare PID/TID creation times before observation. No lookup by bare
PID/TID and no reopening by a stale process-local job handle is permitted.

## Scope

This checkpoint adds the value-only identity contract and exact validator. It
does not roll the durable probe schema, create a watcher or token registry,
duplicate a handle, inspect a process, launch a probe, perform cleanup, use the
network, invoke a receiver/model, or use GPU/ComfyUI.

## Next Boundary

The durable probe-evidence schema must be rolled to carry the exact observer
binding and bind it into record hashes before a concrete native provider can be
implemented or authorized. Existing schema-v1 records remain readable but are
not eligible for native NQ-12 observation.

State: OBSERVER IDENTITY DEFECT CONFIRMED / VALUE CONTRACT IMPLEMENTED /
QUALIFICATION PENDING / SCHEMA ROLL NOT STARTED / NOT STAGED / NOT COMMITTED /
NOT PUSHED / NATIVE EXECUTION HOLD.

## Verification

- focused observer-identity contract: 27 passed / 0 failed;
- bounded EA-4E.92S chain: 615 passed / 0 failed;
- full guarded Hermes Core: 4,228 passed / 35 inherited failures / 6
  deselected / 104 subtests passed;
- exact inherited-failure identity comparison: 35 versus 35, exact match;
- full-run JUnit SHA256:
  `ffb963e81d1caa4a40b93041ed35f78a489afbab8baa9608bd209e867067b766`;
- fake-only denied process attempts: 32;
- filesystem tripwire events: 0;
- prohibited runtime-capability scan: pass;
- whitespace validation: pass.

The first focused run exposed one test-helper ambiguity: explicit `None` was
mistaken for the helper's default binding. A private sentinel corrected the
fixture; production contract semantics did not change.

State: OBSERVER IDENTITY DEFECT CONFIRMED / VALUE CONTRACT IMPLEMENTED /
NON-LIVE QUALIFICATION PASS / SCHEMA ROLL NOT STARTED / NOT STAGED / NOT
COMMITTED / NOT PUSHED / NATIVE EXECUTION HOLD. No watcher, native provider,
probe or resource operation ran.

## Staged Qualification

Exactly this identity contract, focused test and evidence file were staged.
Immutable tree `818cf15048b598087cafd61791921891202ac127`; archive SHA256
`34151eede462c9696d4dd641057ba83aa18d0ac4313e07ad0fd04935f43a0c4c`.
The extracted tree passed the complete bounded EA-4E.92S chain: 615 passed / 0
failed, with fake-only and filesystem tripwire events both zero.

State: EXACT THREE-FILE CHECKPOINT STAGED / FIRST STAGED-EXPORT
QUALIFICATION PASS / EVIDENCE NORMALIZATION IN PROGRESS / NOT COMMITTED / NOT
PUSHED / NATIVE EXECUTION HOLD. The schema roll remains NOT STARTED.
