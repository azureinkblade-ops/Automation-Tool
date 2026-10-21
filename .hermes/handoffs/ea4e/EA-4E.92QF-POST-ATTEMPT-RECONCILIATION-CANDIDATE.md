# EA-4E.92QF Post-Attempt Reconciliation Candidate

This source-only correction responds to the independent 92QE HOLD on ordinary
denials after a possible native directory creation. The unwired owner now
returns `DENY:POST_ATTEMPT_RECONCILIATION_REQUIRED` for every attempted
native call that does not produce an accepted retained handle. This is
conservative even for a sentinel result or a call that throws before its
effect can be observed. It neither claims creation happened nor permits a
retry, path adoption, or deletion.

The specific shape/descriptor/native/catch result is returned separately as
`observationStatus`. `closeStatus` distinguishes no close attempt, a
successfully observed raw or wrapper close, uncertain close, and a handle
retained by the caller. The existing native creation last error and the
observed close error are separate outputs. The existing volume/file identity
outputs now preserve the values obtained from a successful shape observation
even if later descriptor readback fails. These values are partial
observations, not authenticated issuer or installation proof. A successful
close does not clear the reconciliation disposition because the directory
may still exist.

Focused inert owner/shape/descriptor tests passed 32/32; the adjacent
source-only matrix including file identity and descriptor regressions passed
113/113 before staging. These tests compile the candidate and exercise pure
classifiers, pre-call screens, and invalid handles. They do not invoke
`CreateDirectory2W` or exercise a valid native handle. The complete owner
and issuer remain **HOLD pending new independent review and native gates**.
The 92QE one-review authorization was consumed and cannot be reused. Strict
92AT mapped-byte proof remains REJECT. No real receiver/model, Docker
mutation, GPU, ComfyUI, or production action occurred.
