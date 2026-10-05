# EA-4E.92CY receiver-identity host preflight

Status: READ-ONLY HOST INVENTORY / ISOLATION HOLD
Baseline: `e5fe25a8ac17873668a8f60ed02e60ac592e9421`

## Observations

Read-only Windows queries found the interactive account `DAVIDSPC\David`
enabled and in the local Administrators group. `C:` is local NTFS.
`BFE` and `MpsSvc` are running automatically. Enabled local accounts other
than David are `CodexSandboxOffline` and `CodexSandboxOnline`; these belong
to another application boundary and are not candidate EA-4E receiver
identities. No dedicated EA-4E standard account was identified. Disabled
built-in accounts are not candidates. No account, group, ACL, service,
filter, credential, firewall rule, or process was changed.

These observations establish platform prerequisites only. Running BFE does
not prove a user-specific WFP rule exists, applies to loopback, or denies
unrelated clients. NTFS does not prove the proposed per-attempt directory
ACL is present or effective.

## Threat boundary and decision

A new standard local receiver identity with a private profile could deny
ordinary unelevated processes under David's interactive identity access to
its token/config, subject to measured ACL and logon behavior. It cannot
exclude an elevated process acting with local administrator rights. Because
David is an Administrators member, this distinction is material on this
host; do not report a same-user isolation PASS without stating whether
elevated local processes are excluded from the threat model.

Even a SID-scoped WFP connect rule identifies the account, not the unique
Kilo PID. It does not distinguish Kilo from another process legitimately
running under the receiver SID. A one-process-at-a-time job limit is a
candidate containment measure, but Kilo 7.8.3 compatibility and child
process behavior have not been qualified. The 92CR dummy probe is not a
negative test of this policy.

## Next non-live qualification

1. Freeze the exact local adversary model: ordinary unelevated David
   processes, elevated David processes, other receiver-SID processes, and
   privileged SYSTEM/kernel code must each be in or out explicitly.
2. Specify a separately owned standard account, credential owner, broker
   privilege, profile/config path, ACL, gateway port, and rollback plan.
   Do not reuse either Codex sandbox account.
3. Fake-test the admission policy before host mutation: wrong SID, wrong
   endpoint, expired token, replay, unknown process, and crash all deny.
4. Under a separately reviewed host-mutation authorization, test actual
   NTFS token-file denial, WFP loopback filtering, direct egress denial,
   Kilo compatibility, and cleanup. A successful allow test without the
   corresponding negative tests is insufficient.

Until those gates pass, `KILO_GATEWAY_PEER_ISOLATION=HOLD`. The independent
exact 92AT mapped-image-byte proof remains REJECT/HOLD. No real receiver,
provider, model, or native image-proof process was invoked.
