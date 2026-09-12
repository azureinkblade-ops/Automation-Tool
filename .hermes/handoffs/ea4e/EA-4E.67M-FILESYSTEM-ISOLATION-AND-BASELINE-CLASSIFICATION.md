# EA-4E.67M Filesystem Isolation and Baseline Classification

Parent checkpoint: 8ead13ac424ba05adeb278c28ee2c633e0200699.
Scope: test-harness safety only, no production execution-policy changes.
EA-4E.67L's 3186/74/16/6 and 104 subtest results remain historical HOLD.

## Surgical fixes

The OpenCode 25A autouse fixture no longer reads, creates, or removes the live
spool. No spool is necessary for identity/accounting tests. It now rejects
RealOpenCodeProductionExecutor.execute calls explicitly.

Removing the unsafe cleanup exposed two latent complete-path fixture defects:
the invocation policy had no required durable store, and its already-defined
mock executor was not wired into the binding factory. The test now initializes
a temporary SQLite/anchor pair, persists its fake authorization payload, and
binds the existing mock. An exact-once mock execution assertion was added.
Production durable-store/binding semantics remain unchanged.

## Filesystem guard

tools.ea4e67m_filesystem_guard installs a Python audit hook before collection.
Mutation paths must resolve beneath fresh explicit basetemp inside the worktree
or source export. TEMP/TMP and tempfile storage are redirected into that root;
LOCALAPPDATA is preserved because its immutable defaults enter sealed hashes.
Bytecode writes are disabled. SQLite URI paths use structured URI decoding;
remote URI authorities are denied. The null capture device is not a file write.
Outside-root open-for-write, SQLite connection, deletion, directory creation,
rename/link/symlink and common mutation audit events are rejected. Any recorded
violation fails the session. This is a Python-level tripwire, not universal OS
containment, and no complete filesystem syscall coverage is claimed.

## Audit and tests

Repository search inventoried rmtree/unlink/remove/rmdir and AppData references
across tests/hermes_core. The sole explicit hardcoded live-spool recursive
cleanup was the fixed 25A fixture. Representative other cleanup paths originate
from mkdtemp/TemporaryDirectory or tmp_path, not production spool storage.
This search is not proof that arbitrary dynamic/native code has no side effects.

Twelve new isolation tests cover source-fixture cleanup absence, six protected
mutation events, parent escape, encoded SQLite URI admission/rejection, null
capture, actual rmtree rejection with an intact temporary protected sentinel,
and actual executor-call rejection. The sentinel is test-owned, never live data.

Focused final gate: 28 passed / 0 failed / 0 process events / 0 filesystem events.
Expanded candidate ladder before the final two added regressions: 242 passed,
4 separately qualified historical process nodes excluded, both event counts 0.
No full Hermes Core green claim is made.

## Baseline comparison

Tracked source from 8ead13a export, supplemented only by the explicit candidate
filesystem guard and tracked docs/architecture schemas, reproduced:

- Missing frozen Codex executable: baseline and candidate fail the same node.
- Cross-receiver BINDING_LIMIT_EXCEEDED: baseline and candidate fail same node.
- Legacy OpenCode fake qualification FAIL: baseline and candidate same node.
- Claim-concurrency node passes isolated baseline and candidate; the broad-run
  failure is non-reproducing here, not evidence it can be discarded universally.

Final isolated baseline probes: 3 failed / 1 passed / both tripwire counts 0.
Candidate probes likewise 3 failed / 1 passed / both tripwire counts 0.
The initial baseline probe lacked docs schemas and was not valid concurrency
evidence; adding those from the same commit allowed a valid passing rerun.
These classifications apply to these four nodes only, not all historical 74.

## Five-file checkpoint boundary

1. tests/hermes_core/test_opencode_invocation_authorized_live_25a.py
2. tools/ea4e67m_filesystem_guard.py
3. tests/hermes_core/test_ea4e67m_filesystem_isolation.py
4. .hermes/handoffs/ea4e/EA-4E.67L-BROAD-SUCCESSOR-GATE-SAFETY-HOLD.md
5. This EA-4E.67M evidence file

Successor production/test WIP remains excluded. No live spool cleanup/rerun,
receiver/model execution, authorization issuance, activation, GPU, ComfyUI,
server restart or deployment occurred in this safety-repair slice. Original
integration lane untouched. Next: clean export/postcommit gates, then partition
remaining broad-suite failures for isolated reproducible classification.

## Clean Precommit Gate

Staged tree 025a6aeeabf703fa25d780b55537923465f2feb0 was exported with
tracked tools/tests/docs architecture and .gitattributes only into
ea4e67m-index-20260912a. Complete 31/32/33/33A/H/J/M/25A ladder passed
244 tests, with exactly four previously qualified process nodes deselected,
zero process events and zero filesystem events. No untracked source dependency
or successor WIP was needed. The staged diff whitespace check passed.
Only evidence text changed after this gate; production/test source unchanged.
