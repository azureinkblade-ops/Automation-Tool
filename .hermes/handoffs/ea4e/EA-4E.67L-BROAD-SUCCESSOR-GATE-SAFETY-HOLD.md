# EA-4E.67L Broad Successor Gate Safety HOLD

Governing committed checkpoint: 8ead13ac424ba05adeb278c28ee2c633e0200699.
EA-4E.67K seven-file checkpoint remains qualified and pushed; remote exact SHA
verified, ahead/behind 0/0, staged zero. Original integration HEAD remains
18705370d04d809d5979bb7297b71f49d7046f77.

## Raw broader result

Full tests/hermes_core candidate run, strict tools.ea4e67_fake_only_guard,
no cacheprovider, fresh .pytest-ea4e67l-full-fake-20260912a basetemp.
Excluded exactly the four historical and two new durability process tests,
which were separately qualified in the bounded helper envelope.

- 3186 passed
- 74 failed
- 16 setup errors
- 6 deselected
- 104 subtests passed
- 36 subprocess.Popen attempts blocked by the fake-only guard
- Exit code 1; elapsed 101.28 seconds

These results include uncommitted successor WIP, not a committed successor
closure. No full green or all-inherited classification is supported.

## Hard safety boundary

Existing test_opencode_invocation_authorized_live_25a.py autouse fixture
clean_spool_directory calls shutil.rmtree on the hardcoded real path:
C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\spool
at setup and teardown. All sixteen setup errors show WinError 5 at os.rmdir.
The broad run should have been preceded by a filesystem-mutation fixture
audit; subprocess/network tripwires do not contain filesystem operations.
The user's no-deletion constraint must apply to indirect test fixtures too.

No further fixture invocation or permission escalation was attempted. A
read-only directory listing after the run was empty. There is no pre-run
directory snapshot, so absence of partial content deletion cannot be proven;
do not describe this broad run as having no runtime filesystem effects.
Do not restore/delete/reset live spool state speculatively.

## Other observed groups, not exhaustively classified

- Codex binary tests reference a missing frozen executable path.
- Cross-receiver predecessor tests report BINDING_LIMIT_EXCEEDED.
- Local worker/coordinator probe tests hit process-denial tripwires.
- Legacy OpenCode fake invocation tests report the required durable invocation
  authorization store is absent.
- OpenCode adapter/parser tests and one claim-concurrency test also failed.

No baseline reproduction was performed after discovering the unsafe fixture.
Do not label the entire raw failure set pre-existing or weaken production
durability/binding policy to make legacy tests pass.

## Controlling state

EA4E67K_CHECKPOINT=COMPLETE_AND_SYNCHRONIZED
EA4E67L_BROAD_GATE=HOLD
SUCCESSOR_WIP=UNCOMMITTED_NOT_DEPLOYED
SUCCESSOR_COMMIT=NO
PRODUCTION_ACTIVATION=NO

Next safe scope: audit all filesystem mutation/runtime path fixtures; move
tests to explicit temporary storage without touching the live spool; partition
metadata/real-process probes from strict fake-only gates; reproduce remaining
failures against isolated committed baseline and candidate trees; classify each
before any successor checkpoint. No further automated progression in this run.
