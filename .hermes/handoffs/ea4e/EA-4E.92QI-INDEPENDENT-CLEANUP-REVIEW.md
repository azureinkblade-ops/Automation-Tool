# EA-4E.92QI Independent Cleanup Review

One separately approved, independent reviewer inspected ten exact pinned
`<commit>:<path>` blobs at source commit
`8f24ded2aaee6d3a742a1613e465f3d56d744fd6`. Every required Git blob
SHA-1 matched the review packet before substantive review. The attributable
report is Codex thread `01a16124-3d41-7c91-a721-b235fbddfd4f`.

## Findings And Verdicts

1. **High, existing native-issuer integration blocker.** The unwired owner
   accepts caller-supplied parent, manifest, and SID without independently
   proving their provenance, persistent-ACL volume support, scoped privilege,
   first-child absence, or limited-client effective rights before creation
   (`tools/Ea4eDirectory2OneAttemptCandidate.cs:58-98`). This is an
   integration blocker, not an observed production exploit.
2. **92QG cleanup gap closed at source level.** Both wrapper `Dispose()`
   branches catch ordinary exceptions, preserve wrapper-close uncertainty,
   and reach the mandatory post-attempt reconciliation classification
   (`tools/Ea4eDirectory2OneAttemptCandidate.cs:155-203`). Raw-close
   uncertainty is set before invocation and cleared only after observed
   Boolean success (`:112-125`). The reviewer found no synchronous
   double-close or implicit retry. Fatal out-of-memory and stack-overflow
   exceptions are explicitly rethrown; the guarantee is not unconditional.
3. Creation and close errors/status, observation result, and partial file
   identity remain distinct. A thrown close may leave `closeError == 0`, but
   the uncertainty status prevents treating that as an observed close.
   Caller ownership transfers only after shape and descriptor acceptance.

Narrow cleanup/reconciliation correction: **source PASS**. Complete source
owner: **HOLD**. Authenticated native issuer: **HOLD**. Strict 92AT mapped-byte
proof: **REJECT**. The review did not run tests or a native owner; the
committed-tree 113/113 inert tests do not establish valid-handle behavior,
native ABI/environment qualification, or production readiness. No native,
Docker, receiver/model, GPU, ComfyUI, or production action occurred.

Narrowest next non-live action: an inert fault-injection harness for throwing
wrapper disposal and raw close, asserting uncertain close and mandatory
reconciliation while keeping the owner unwired. The single review approval
was consumed by this pinned review.
