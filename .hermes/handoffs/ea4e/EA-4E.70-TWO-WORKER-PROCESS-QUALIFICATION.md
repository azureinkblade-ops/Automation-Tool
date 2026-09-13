# EA-4E.70 - Two Worker Process Qualification

Baseline: a24e4b12105f261ef3e9ecab0343a7f19d0842a3.

RESULT: HOLD / PIPE-DESCRIPTOR QUALIFICATION REQUIRED. NOT COMMITTED / NOT PUSHED.

Working-tree run: 0 passed / 2 failed; two Popen creation attempts, zero returned child handles, zero process-guard prohibited events, two filesystem tripwire events. Both failures occurred at subprocess.Popen.__init__ opening p2cwrite with io.open(..., 'wb'), before _execute_child. Read-back of the installed standard library confirms child launch occurs only after pipe wrapping. No child process was launched by these calls; no positive real-worker or cleanup proof was obtained.

The filesystem guard correctly denies unidentified descriptor mutations. Do not disable it or permit arbitrary descriptors. Next prerequisite is a test-owned, narrowly qualified pipe descriptor rule limited to the validated Popen constructor's owned stdin pipe, the exact active launch scope/thread, and exact frozen call path, with negative tests for unrelated descriptors, files, nodes, and escaped scope. Review/prove that rule fake-only before another bounded process run. The current two-attempt envelope is exhausted for this invocation; no automatic live retry was performed.

Bounded authority: two named dedicated tests, one creation attempt each, two total. Only the frozen Python interpreter and guarded entrypoint wrapping canonical local-worker argv are admitted. No receiver, agent, model, shell, network, GPU, or ComfyUI workload is permitted. Production activation remains off.

Three new test-owned files: separate qualification process guard, dedicated two-probe tests, this evidence. Existing fake-only and filesystem guards remain unchanged. Parent guard is installed before test collection; shell/network are denied, and any unexpected process attempt fails the gate. Filesystem guard still confines parent mutations to fresh basetemp. Child policy is installed by the guarded entrypoint before loading the deterministic worker.

The first probe checks terminal successful acknowledgement and durable STARTED row. The second deliberately exceeds communication timeout, then verifies owned cleanup terminates/reaps the child and closes every pipe. Session-final cleanup also covers all returned child handles and fails on cleanup errors or an incomplete two-attempt count.

Limits: these probes do not deliberately exercise child network/out-of-root denial, native syscall isolation, every original adapter/coordinator fault path, or crash durability. Those remain required qualification work. Bootstrap dependencies use the declared canonical LF source hashes; the interpreter and workload helper retain exact-byte pins. This does not establish production readiness or full successor green.

Verification must run in working, staged-only, and committed exports with explicit --ea4e70-two-worker-probes, fresh basetemp, dedicated process guard, unchanged filesystem guard and nonlive report-host plugin. The previous 76-test fake-only gate remains a separate acceptance gate.
