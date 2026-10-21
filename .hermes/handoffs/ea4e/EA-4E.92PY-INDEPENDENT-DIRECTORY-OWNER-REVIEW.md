# EA-4E.92PY Independent Directory Owner Review

Baseline: `2eb7b2e53b2642b0f01ee2f790cd82f8a34ca737`. One separately
delegated read-only reviewer returned the findings below. No source was edited
by the reviewer. The local caller re-queried all eight requested Git blobs;
all match the SHA-1 values in the Obsidian 92PY request. The reviewer's final
report did not enumerate its own integrity-query output, so the local
verification is recorded separately from reviewer attribution.

## Findings

1. **Medium - exceptional raw-handle ownership gap.** After the native call
   returns a non-sentinel handle, `Ea4eDirectory2OneAttemptCandidate.cs`
   screens it and constructs `SafeFileHandle` before assigning `owned`.
   Constructor failure, especially allocation failure, can leave the raw
   handle outside the method's `finally` disposal. The result does not become
   success or cause retry, but exact-handle cleanup is incomplete (lines
   58-63 and 92 at the pinned baseline).
2. **High - issuer and effective-rights proof absent.** The input screen
   compares supplied path and descriptor values but does not authenticate
   known-folder, manifest, app SID, ACL-capable volume, issuer token/privilege,
   or first-child absence. Exact-handle descriptor readback is structural;
   it does not prove client-token effective rights or observed no-delete
   sharing (owner lines 16-27; descriptor reader line 189).

Normal source flow makes at most one five-argument native call per invocation,
immediately captures last-error, rejects zero and minus-one, and has no
path-based adoption, retry, or removal. It uses the returned handle for
repeated shape/path/identity checks and descriptor readback; denial disposes
the wrapper while candidate return transfers it. Those are source claims,
not native runtime observations. The tests call only the pre-call screen.

Source-only owner: **HOLD** pending exceptional-handle cleanup correction.
Native issuer: **HOLD** pending external authentication, runtime semantics,
sharing, and effective-rights proof. Live receiver/production readiness:
**REJECT** as a claim; strict 92AT mapped-byte proof remains REJECT. The
narrowest next non-live step is to close the post-return/pre-wrapper gap and
review the newly pinned source. No native operation, receiver/model, Docker
mutation, GPU, ComfyUI, or production activation occurred.
