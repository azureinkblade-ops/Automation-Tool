# EA-4E.92OC secondary descriptor-screen diagnostics

Status: NON-LIVE SOURCE-ONLY / NATIVE RETRY HOLD.
Governing parent: `02e0ba46a885fcda3fa1e9388f2e7d643c8d10bb`.

The one actual 92OB native readback-only run exited `31`, which previously
collapsed every secondary descriptor-screen denial. This checkpoint preserves
the secondary screen's specific denial in the readback result and assigns
distinct nonzero exit codes for its known reasons. Earlier owner/group/ACE
count checks remain earlier fail-closed checks; the tests respect that order.

The inert mapping and adjacent source/descriptor/creator/protected-store
working-tree matrix passed 126/126. It did not invoke the native mode or
reopen a protected pipe. The 92OB result remains HOLD, not retroactively
qualified. No client, Docker mutation, Kilo/OpenCode receiver, model,
credential, GPU, ComfyUI, or production activation was exercised.

The staged source export's inert readback and descriptor-screen tests passed
48/48.

A future native run requires a new exact executable hash and separate
one-shot authorization. Even a structural readback pass would not close the
limited-client rights or trusted issuer gates of 92NK.
