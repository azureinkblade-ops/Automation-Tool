# EA-4E.68 - Guarded Worker Entrypoint

Baseline: cec0038c59c4414e945082b5985855f1043c5f72.

Scope: a new test-owned entrypoint, six fake-only sequencing tests, and this evidence. No existing production modules, guards, worker fixture, or protected WIP are changed.

The entrypoint requires the canonical node, isolated root, and original worker argv. Existing admission validates paths, hashes, environment, fault flags and state location. Only after validation does it install the child policy and load the frozen deterministic worker. Guard/admission modules are trusted bootstrap dependencies; this is not a claim that all imports occur under an OS sandbox.

No processes are launched. Tests replace policy installation and worker loading; they prove ordering and fail-closed behavior without installing an irreversible hook in pytest. Child admission starts with empty accounting because aggregate launch accounting belongs to the future parent launcher, not this entrypoint.

Acceptance gate: six dedicated tests plus the previous 63-test gate; verify working, staged-only and committed exports under unchanged fake-only and filesystem guards.

Next: qualify a hash-frozen, test-only parent launcher and explicit process envelope, including aggregate budgets and owned cleanup. No launch exception, receiver/model activity, production activation, GPU work, or full successor-green claim is authorized by this artifact.
