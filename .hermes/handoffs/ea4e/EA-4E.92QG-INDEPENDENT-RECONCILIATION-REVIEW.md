# EA-4E.92QG Independent Reconciliation Review

One separately approved, independent reviewer read all ten pinned
`<commit>:<path>` blobs from
`bde1b97425d210773539f118b4db7f0a162ed6d8`. Every required SHA-1
matched before substantive review. The attributable report is in Codex
thread `01a160e5-2df0-7563-9db5-1ae5628f81d7`.

## Findings

1. **High, existing native-issuer integration blocker.** The owner still
   receives caller-supplied parent/manifest/SID values and does not establish
   their provenance, persistent-ACL volume capability, privilege,
   first-child absence, or limited-client effective rights before invoking
   native creation (`tools/Ea4eDirectory2OneAttemptCandidate.cs:58-98`). No
   committed C# caller was found. This is not an observed production exploit.
2. **Cleanup-exception qualification gap.** `Dispose()` at owner lines 158
   and 167 runs in the outer `finally`, outside the catch. If it throws a
   catchable exception, execution does not reach the reconciliation
   classification at lines 177-185. The wrapper records release state only
   after `CloseHandle` returns, so a thrown release could remain unobserved.
   The reviewer did not demonstrate this with a valid native handle; it is
   a source contract gap, not a confirmed runtime occurrence.

For normally completing cleanup paths, sentinel, readback denial, caught
observation exception, and Boolean raw/wrapper close failures produce the
primary reconciliation-required disposition. A handle transfers only after
complete shape and descriptor acceptance. Creation error, close error and
status, observation status, and any partial identity remain separate. The
reviewer found no concrete double-close, retry, path adoption, or deletion
path in the inspected synchronous flow. It did not rerun the reported
113/113 inert tests, which do not execute native creation or failure cleanup.

Verdicts: the prior narrow synchronous ownership/Boolean-close **PASS** is
preserved; the 92QF reconciliation correction **PASS only when cleanup
completes normally**; complete source owner **HOLD**; native issuer **HOLD**;
strict 92AT mapped-byte invariant **REJECT**. No native or production
readiness follows. The reviewer edited no files, ran no tests or native
owner, created no objects, and invoked no live services.

Narrow next non-live action: make catchable cleanup exceptions produce an
explicit uncertain close status while preserving mandatory post-attempt
reconciliation, then obtain a new pinned independent review. Do not retry
the close or delete/adopt by path. Inert fault injection can validate only
control flow.
