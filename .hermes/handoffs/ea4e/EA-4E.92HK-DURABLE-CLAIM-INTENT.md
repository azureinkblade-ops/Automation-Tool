# EA-4E.92HK Durable Claim Intent and Concurrent Qualification

Status: NON-LIVE / FAKE-ONLY / PARTIAL. Parent: EA-4E.92HJ.

Source review found a retry gap after an ambiguous authorization claim. A
pre-commit failure could leave the authorization unconsumed and the receiver
fence absent, allowing a later call to try again. The claim owner now commits
one per-attempt intent in the delegation database before touching the durable
authorization claim. Any repeat call after that intent returns UNKNOWN and
cannot reissue, re-consume, or create a new fence. This deliberately favors
manual reconciliation over an unsafe automatic retry.

Two independent owners racing on the same accepted Kilo attempt yielded one
FENCED result and one UNKNOWN result, with one consumed authorization and
one start fence. The concurrency test passed in ten additional runs. An
injected pre-commit authorization failure leaves a durable intent and an
unconsumed authorization; after reopening the authorization store, claim
returns UNKNOWN and issue is denied. The existing after-consumption fence
fault and cancellation-between-claims tests remain green. The broader
delegated/issuer/provisioner ladder passed 156 tests, 0 failed.

The intent itself grants no authority. `FENCED` still means no receiver was
started. This is not the full fault matrix: post-database/pre-anchor failure,
crashes at every persistence edge, cross-process races, production trigger
ownership, actual PID/argv/terminal-byte proof, and result return remain
open. No real receiver/model, network, Docker, GPU, ComfyUI, or production
activation was invoked. `PRODUCTION_READY=NO`.
