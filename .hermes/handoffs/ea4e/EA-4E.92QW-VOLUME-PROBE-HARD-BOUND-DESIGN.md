# EA-4E.92QW Volume Probe Hard-Bound Design Decision

Status: non-live design only. No launcher, protected installation, native
qualification, issuer authority, or receiver/model action is authorized.

## Decision

The unwired 92QV Python runner is a useful fake-tested denial wrapper, but
it is not the hard containment boundary for a native probe. The 92QU
independent review found blocking hashing, spawn, and stream closure, plus
wall-clock and cleanup limits. Its reader-start finding was corrected in
92QV; the medium finding is not closed by another timeout check in the same
Python call stack. Keep that runner unwired from the trusted issuer.

The next candidate is a separately protected, self-contained supervisor
with an independent watchdog. It must own the complete operation from
approved image selection through final cleanup. The existing
`tools/ea4e92s_windows_job.py` prepares a job with fake-tested limit
readback, but has no process launcher, watchdog, or native enforcement
qualification. `tools/ea4e92s_containment_lifecycle.py` is an injected
fake-only lifecycle. Neither may be treated as the proposed supervisor.

## Required proof

1. Independently reviewed installation pins the supervisor, probe image,
   runtime/imports, configuration, and working-directory closure under an
   admin-controlled versioned directory. Verify bytes and effective
   write/replace/delete/DACL/owner rights from retained handles, including
   ancestors and reparse status. A worktree hash is not approval authority.
2. A durable one-use grant binds operator SID and elevation, ceremony,
   expected source/installation/store generation, exact action and
   deadline. Before any launch, consume the grant in a distinct issuer
   ledger. Uncertainty is terminal; no automatic retry.
3. The supervisor starts only the pinned probe with an explicit executable
   identity, exact arguments, restricted environment, fixed directory,
   bounded inherited handles, and creation-time membership in a configured
   owned Job. A post-create assignment window is not accepted. Verify job
   membership and the observed process/image identity before allowing work.
4. An independent watchdog uses monotonic elapsed time to terminate the
   owned Job on expiry, output overflow, broker failure, or uncertain
   observation. It must remain effective when the worker blocks in file I/O,
   spawn, capture, or closure. Closing a kill-on-close Job is useful only
   when no unintended inheritor retains its handle; that condition needs
   proof. Bound capture incrementally and preserve a cleanup-uncertain
   terminal state if owned resources cannot be reconciled.
5. A native qualification matrix must exercise delayed hashing, stuck
   launch, pipe backpressure/overflow, blocked close, child escape attempt,
   watchdog death, clock adjustment, image substitution, and ACL/reparse
   drift with dedicated inert probes. Tests of injected fakes cannot prove
   the Windows behavior. Each native attempt requires a new exact bounded
   authorization; no real receiver/model is in this matrix.

The exact 92AT mapped-byte requirement remains separate and REJECT. Job
membership and image-path/hash evidence do not attest mapped section bytes.
Even a qualified volume supervisor would not by itself permit trusted
creation, Kilo/OpenCode execution, or production activation.

Related governing evidence: `EA-4E.92QU-INDEPENDENT-CORRECTED-VOLUME-SUPERVISOR-REVIEW.md`,
`EA-4E.92QV-READER-START-TRACKING-CORRECTION.md`,
`EA-4E.92JY-PROTECTED-ISSUER-DEPLOYMENT-CONTRACT.md`, and
`EA-4E.92S-WINDOWS-JOB-PARTIAL.md`. Microsoft documents
[`CreateProcessW`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)
and [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects);
these APIs do not supply the missing installation, ledger, or mapped-byte
proof by themselves.
