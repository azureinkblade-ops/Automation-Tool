# EA-4E.92IC Delegated Linux Kilo Mount Candidate

Status: NON-LIVE / SOURCE-BOUND CANDIDATE / PRODUCTION_READY=NO.
Baseline: `19c0f4a73c2b968cc07b14752072ba8e0bbde465`.

The 92IB attempt-unique reserved ping plan is now connected to the existing
92DP reviewed-input and separate writable-runtime-copy materializer. The
candidate builder revalidates the reserved plan and live preclaim window,
rehashes both prepared file copies, and returns the exact two source paths and
container destinations. A second plan check catches authority changes during
the file reads. The returned candidate explicitly has
`effective_mounts_checked=False` and `launch_authorized=False`.

The existing mount verifier called `Path.is_junction()`, unavailable in the
installed Python 3.11 runtime. It now denies Windows reparse points through
`st_file_attributes`, retaining symlink checks and working on this runtime.
This is an input-verification portability correction, not a relaxation of the
link policy.

Focused tests cover a reserved plan, separate reviewed/runtime sources,
changed task plan, changed runtime bytes, unreserved attempts, and the
pre-3.12 reparse-point path. The affected 92DP/92DR/92H/92I ladder passed
151 tests, zero failed. No Docker object, receiver, gateway, credential,
network call, model, GPU, ComfyUI, or production activation was used.

The candidate is not durable, cannot prove source immutability after return,
and does not establish effective Docker mounts. The future container owner
must select one candidate per attempt, revalidate the source bytes at the
admission boundary, compare trusted daemon-observed mounts and config, and
account for Kilo's runtime config rewrite. Network/peer binding, retained
terminal bytes, model/provider credentials, and bounded live authority remain
separate open gates. The strict 92AT exact mapped-byte proof is unchanged.
