# EA-4E.92MW pure issuer-admission candidate

Status: NON-LIVE CANDIDATE / NOT AN ISSUER / PRODUCTION HOLD.
Parent: `99cb2baf74ed40ad6ce90e7911c27e7cc5b9c572`.

This checkpoint composes the 92MV parsed policy with the 92MO token and 92MP
on-disk image comparisons, plus store ID/epoch, governing source commit,
authority ID, and bounded TTL comparisons. A positive result is deliberately
named `CANDIDATE_MATCH_NOT_AUTHORITY`. The tests inject fake observations;
foreign SID, non-elevated token, changed executable path/hash, store drift,
source/authority drift, invalid time, and excessive TTL deny.

Changed files: `tools/Ea4eProtectedIssuerAdmissionCandidate.cs`,
`tests/hermes_core/fixtures/ea4e92mw_issuer_admission_probe.cs`, and
`tests/hermes_core/test_ea4e92mw_issuer_admission_candidate.py`.

Working-tree qualification: 49 passed / 0 failed across admission, policy,
token, and image tests. These tests run only local compiler/test-probe
processes. No protected installation, UAC, Docker mutation, receiver/model,
GPU/ComfyUI use, or production activation occurred.

The observations and policy hash still come from the caller in this pure
candidate. Production use requires a protected installed closure, independent
operator-approved policy hash, actual elevated token and installed image
observations, qualified app-instance and Docker identity, trusted current
authority and clock, v5 store bootstrap, and exact one-shot ceremony. The
92MP witness hashes an on-disk file, not mapped image bytes. The strict 92AT
invariant remains REJECT/HOLD; the accepted local-container profile is
separate.
