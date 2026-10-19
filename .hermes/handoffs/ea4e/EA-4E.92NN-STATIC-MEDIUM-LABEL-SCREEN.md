# EA-4E.92NN static medium-label screen

Status: NON-LIVE CANDIDATE / NATIVE QUALIFICATION HOLD.
Parent: `63ff858b0072de01baeea48a942bd1cd924b9532`.
Profile: accepted 92DE local-container profile only.

The approved 92NM design requires one explicit medium-integrity
`NO_WRITE_UP` mandatory label. The 92NL source screen now parses the
descriptor's SACL and requires exactly one mandatory-label ACE, policy
`0x00000001`, SID `S-1-16-8192`, and no ACE flags or trailing bytes.
Absent, high, low, wrong-policy, and duplicate label cases deny. The
synthetic matrix has 32 cases. The only non-denial result remains
`CANDIDATE:STATIC_ONLY`.

This parses proposed SDDL only. It does not create a pipe, prove the
elevated creator can set that label, read back a real pipe's label, prove
effective limited-token access, or exclude other medium callers. The
owner, DACL, process-bound challenge, one-shot accounting, and native
negative probes remain required. No UAC, issuer, Docker, receiver/model,
GPU/ComfyUI, or production activation occurs here.
