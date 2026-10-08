# EA-4E.92FH Fake Image Index/Manifest Binding

Status: NON-LIVE CONTRACT CORRECTION PASS / NEW DIAGNOSTIC HOLD
Baseline before this change: `fa1035cfbb9ec16646053b56e60e00200c397f8d`
Date: 2026-10-08 (America/Phoenix)

The earlier accepted 92DK/92DL Docker evidence established that a created
container's `Image` field binds to the local image **index**, while a
`--platform linux/amd64` image inspect identifies the selected manifest.
92EZ already pinned both values, but the new 92FB and 92FG checkers had
compared the container field with the platform-selected value. This change
makes the plan carry explicit gateway/client index IDs and requires those in
created and running container records. The read-only image preflight still
checks each selected Linux/amd64 image identity and repo digest; no acceptance
condition was replaced with an unpinned value.

The complete affected fake-only ladder passed 101 tests with zero failures,
including two explicit wrong-manifest regression cases. No Docker
object was created or started for this correction. The 92FE one-shot stopped
at a bundled identity denial without a saved per-field record; its exact
historical cause remains **unknown**, not retroactively relabeled as an index
mismatch. A new bounded diagnostic is still required to observe the current
created-state fields.

`INDEX_MANIFEST_BINDING_CORRECTED=YES_FAKE_ONLY`
`92FE_HISTORICAL_SUBFIELD_KNOWN=NO`
`NEW_DIAGNOSTIC_EXECUTED=NO`
`RECEIVER_EXECUTED=NO`
`PRODUCTION_READY=NO`
