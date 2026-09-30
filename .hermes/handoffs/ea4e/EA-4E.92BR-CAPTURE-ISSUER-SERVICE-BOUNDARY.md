# EA-4E.92BR Capture Issuer Service Boundary

Non-live candidate design at `256b2d38beef5384b8d67914013429059a40a37a`.
The separate Windows service identity is a design assumption, not an approved
deployment choice. No service, account, key, certificate, approval, or capture
authority is created by this document.

## Existing boundary

`CaptureQualificationArtifact` validates canonical fields and current material.
`CaptureQualificationStore.persist_issued()` persists an externally supplied
artifact and issue-request hash; it does not authenticate either an operator or
issuer. Its database and anchor use unkeyed hashes and assume trusted local
storage. A caller able to invoke the store and rewrite both files is outside
that protection. The existing production activation issuer and its configured
operator string are different authority and cannot be reused here.

Read-only preflight found no relevant issuer service. The current process is
`DAVIDSPC\David`; certificates observed under `CurrentUser\My` are in that
same user context. No private key was accessed. The expected local SDK source
paths were absent, so provider behavior remains separately unqualified.

## Candidate trust split

1. An operator approval source, independently authenticated by the broker,
   approves the canonical issue-request digest and capture artifact digest.
   A caller-supplied operator ID or an app button alone is not approval.
2. A dedicated Windows service principal owns the issuer signing capability,
   capture database, anchor, and issuance journal. The app and receiver run
   without access to its private key or write access to those files. The
   service denies unsigned, stale, conflicting, cancelled, or replayed
   requests before persisting anything.
3. The app may submit a candidate request and display status. It cannot sign,
   directly call `persist_issued()`, or edit the service-owned store. The
   receiver may consume only a verified, one-start authorization through a
   separately admitted route. It cannot approve, issue, or repair authority.
4. Merely separating the service account is insufficient if any same-user
   process can ask it to sign without an independent approval. Windows ACLs
   alone cannot distinguish the app from a receiver running under the same
   principal. The approval channel and service API must fail closed even when
   an untrusted same-user process submits a syntactically valid request.

## Receipt and admission contract

The receipt must bind a versioned schema, issuer/key identity, unique approval
and issue-request IDs, exact canonical issue-request hash, exact artifact hash,
operator approval evidence ID, source commit, receiver/run/task identity,
executable/config/transport/model/provider-budget identities, UTC issue and
expiry times, nonce, and one-start limit. The service signs the canonical
receipt only after it has independently verified approval and durably reserved
the unique issue ID. The app's verifier pins the issuer public identity and
checks signature, every bound field, validity window, revocation/cancellation,
and durable one-start state before any capture launch. No field is inferred
from a matching display name or version string.

The implementation must specify the signing algorithm and a reviewed crypto
provider, exact canonical bytes, key rotation/revocation rules, service
identity and key ACLs, authenticated approval mechanism, service API ACLs,
store ownership, and crash ordering. None is selected or provisioned here.
Issuer verification belongs at the issuance/admission boundary, before
`persist_issued()`; leaving the store publicly callable would bypass it.

## Qualification and stop conditions

Non-live qualification must prove denial for a forged/unsigned receipt,
wrong key, mismatched digest or identity, stale approval, duplicate/conflicting
issue, expired or revoked authority, service restart, interrupted store write,
and a same-user unapproved caller. It must prove the receiver cannot read the
key or write the service-owned store. Fake tests alone do not prove the Windows
principal, ACL, approval source, or installed receiver behavior. A real service
setup requires a separate deployment review and explicit authorization.

Provider containment remains a different gate: one process start is not one
upstream model call. The installed OpenCode SDK request/streaming behavior,
durable no-refund call budget, receiver egress restriction, and CPU policy
must be qualified independently. The EA92S exact mapped-byte invariant is
still REJECT on available evidence and cannot be replaced by a PE hash.

Current result: `SERVICE_DESIGN=CANDIDATE_NONLIVE`,
`TRUSTED_ISSUER=UNBOUND`, `PROVIDER_ONE_CALL=UNPROVEN`,
`EA92S_EXACT_MAPPED_BYTE=REJECT`, `PRODUCTION_READINESS=HOLD`.
No receiver/model/provider, GPU/ComfyUI, or production activation is allowed
by this checkpoint.
