# EA-4E.92CZ administrator-in-scope trust boundary

Status: OPERATOR THREAT-MODEL DECISION / LOCAL ISOLATION REJECTED
Baseline: `bacee7bed348aaee1d51b5c82b74c2b540acaca1`

The operator explicitly chose to treat processes with administrator
privileges on the current Windows PC as potential attackers. This decision
supersedes the 92CX dedicated-local-account candidate for production. The
92CY host preflight found the interactive account in Administrators.

## Consequence

A new local standard account, NTFS ACL, Windows Filtering Platform user/port
rule, AppContainer profile, local service, or loopback token cannot be the
sole protection against an elevated administrator on this PC. An
administrator can recover access to protected files and can obtain debug
privilege over other local processes. Local firewall policy, broker state,
and evidence produced solely by this host are within the adversary's
control. These controls may still reduce accidental access, but must not be
reported as satisfying the chosen threat model.

A VM or container whose administration and storage remain under this same
host administrator is not automatically an independent trust boundary.
Hardware-backed isolation/attestation would require its own exact evidence;
none is qualified here. Do not relabel the two existing Codex sandbox
accounts as an EA-4E boundary.

## Candidate independent boundary

Use a separately administered execution host or service outside the local
administrator's control. That host must own the authorization issuer,
durable attempt and one-send stores, receiver executable/config, gateway,
upstream credential, audit log, and cleanup authority. This PC is an
untrusted submission client only. Moving just the token or gateway while
leaving Kilo and the issuer on this PC is insufficient: an elevated local
process could alter the task, impersonate the receiver, or forge local
evidence.

The remote host must not treat possession of a credential stored on this PC
as operator approval. A canonical task request is accepted only after
independent authorization under the remote host's policy, bound to exact
task hash, source and receiver identities, model route, capability scope,
TTL, one-attempt budget, and cancellation state. How that independent
approval is obtained is not selected here; a login session or API key
controlled by this PC is not sufficient on its own. The remote administrator
and its trusted hardware/software base are explicitly outside this local
attacker model and need a separate deployment review.

## Qualification sequence

1. Freeze the remote trust owner, host class, credential/approval channel,
   network endpoint, source deployment path, and rollback owner. No host or
   cloud resource has been provisioned by this decision.
2. Fake-test that local submissions cannot issue, claim, alter, or replay
   authority; remote state must deny stale/mismatched task and receiver
   hashes, excess sends, and cancellation races.
3. In a separately authorized environment, run negative tests from an
   elevated local process: it cannot read remote secrets, mutate remote
   stores, bypass approval, consume the sole send, or impersonate a result.
   Record the remote-side audit independently of this PC.
4. Requalify the exact receiver binary, custom-provider route, request
   identity/size contract, and containment on that host before any real
   receiver/model use. The consumed 92CR dummy probe is not reusable.

The exact 92AT mapped-image-byte invariant remains a separate independent
REJECT/HOLD. A different host does not magically provide section-byte
attestation; file ID, post-create file hash, App Control PE hash, or a
successful fake test still cannot mint `VERIFIED_SUSPENDED`. If no supported
mechanism meets that invariant on the selected platform, production remains
blocked under the retained contract.

`LOCAL_ACCOUNT_ISOLATION_FOR_SELECTED_THREAT_MODEL=REJECT`
`INDEPENDENT_EXECUTION_BOUNDARY_QUALIFIED=NO`
`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`
`PRODUCTION_ACTIVATED=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`

## Primary references

- [Windows takeown](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/takeown)
- [Windows debug privilege](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/debug-privilege)
- [92BA independent staging review](EA-4E.92BA-INDEPENDENT-STAGING-PROOF-REVIEW.md)
