# EA-4E.92CX Isolation and image-byte proof design

Status: NON-LIVE DESIGN / BOTH PRODUCTION GATES HOLD
Baseline: `0635f5f480dca8b1a803e39e98b6f359982d706d`

This packet responds to the request to work on receiver isolation and the
exact 92AT mapped-image-byte proof. It authorizes no account, service,
firewall, driver, ACL, listener, process, receiver, provider, or model change.
The spent 92CR one-shot probe is not reusable.

## 1. Receiver isolation candidate

Use a dedicated, non-administrator local identity for the Kilo receiver,
distinct from the interactive Automation Tool user and the gateway owner.
The trusted broker alone provisions one per-attempt config and local bearer
token in a protected directory accessible to that identity and SYSTEM, not
to the interactive user's unprivileged token. The upstream provider key
remains in the gateway only. Kilo receives only the local gateway endpoint
and short-lived per-attempt token. No account or secret is provisioned by
this design.

The gateway may not infer a Windows process identity from HTTP or the token.
It must pair token validation with an OS-enforced admission boundary for the
gateway port. A candidate is Windows Filtering Platform authorization at
`ALE_AUTH_CONNECT_V4` using the receiver SID, exact destination, protocol,
and port. This is a *candidate*, not an existing rule or proof that loopback
is filtered as intended on this host. A port-only firewall rule, executable
pathname rule, named-pipe PID check on a separate connection, or token alone
does not meet this gate. The gateway still claims its durable one-send budget
before any upstream send, never refunds it, and refuses replay.

The trust boundary excludes Administrator/SYSTEM and compromise of the
dedicated receiver identity. It does not trust other processes under the
interactive account. Processes legitimately running under the receiver SID,
including Kilo children, remain an explicit residual risk; do not claim
per-PID authentication from a SID-based WFP decision. If the requirement is
to exclude *all* other processes sharing that SID, this candidate is HOLD
until a stronger process-bound mechanism is demonstrated. The operator has
not approved weakening that requirement.

Before any host mutation, separately review the exact account owner,
credential storage, logon method, token privileges, profile loading, ACLs,
network policy owner, rollback, and cleanup. The broker must fail closed if
it cannot prove the process token SID, token-file ACL, gateway port filter,
and exclusive one-attempt state. No ambient profile, inherited secret, or
unreviewed outbound network route is allowed. Kilo's actual operation with
the isolated profile and exact custom-provider route requires a fresh,
bounded qualification; the historical inert probe does not establish it.

### Isolation acceptance tests

1. Fake-only tests deny wrong SID, missing/expired token, wrong port, body,
   route, model, and repeated send without consuming a second upstream call.
2. In a separately authorized host test, an ordinary process under the
   interactive user cannot read the config/token or connect to the gateway
   port; a receiver-SID process can reach only the approved local route.
3. Verify actual WFP loopback classification and denial on this Windows
   build, not just the presence of a rule. Capture policy identity and
   negative results. Confirm no direct provider egress from Kilo.
4. Verify cancellation, crash, token deletion, account/session teardown,
   and gateway shutdown leave no usable token or send budget. Any uncertain
   cleanup is sticky UNKNOWN, not permission to retry.

Until these pass, `KILO_GATEWAY_PEER_ISOLATION=HOLD`.

## 2. Exact mapped-image-byte proof

The user retained the exact 92AT requirement. The 92AY/92BA independent
reviews rejected substituting pathname, file ID, a later file hash, or App
Control PE hash for the bytes represented by the created image section.
This design preserves that decision.

Documented Windows process-create and load-image notifications can identify
the executable file object or report image mapping. The file-system section
synchronization callback reports section-creation parameters. None of the
reviewed contracts supplies a loader-attested digest of the specific image
section or a documented equality between its source bytes and a user-mode
file hash. A `SEC_IMAGE` view has PE image semantics rather than being a
raw byte-for-byte file view. Combining the three callbacks is therefore a
research lead, **not** a valid positive proof. No driver is proposed for
deployment on this evidence.

A valid candidate must answer all of these with supported, independently
reviewable evidence before a positive creator is written:

1. Identify the exact section object mapped as the *initial executable* of
   the newly created, still-suspended process, not merely the file object or
   a later image-load event. Bind it to the owned creation attempt.
2. Measure or attest the bytes represented by that section under a specified
   PE transformation model, and demonstrate how this measurement proves
   equality to the reviewed runtime payload. A raw process-memory hash or
   file-ID-plus-hash is not an acceptable shortcut.
3. Exclude a pre-existing section, alternate stream, writer, writable map,
   namespace substitution, and time-of-check/time-of-use races under the
   declared attacker model. A fresh protected file is useful provenance but
   is not by itself section-byte proof.
4. Specify an atomic fail-closed observation before any thread resume, with
   bounded wait, exact handle ownership, termination, and no second process
   attempt on ambiguity. An unavailable/null observation must deny.
5. Obtain independent Windows loader/filesystem review of the complete
   mechanism and a separately authorized host qualification on the pinned
   build. Fake tests can validate denial logic only.

The current reviewed Windows interfaces do not satisfy item 2. Therefore
`TRUSTED_IMAGE_BINDING_QUALIFIED=NO` and `VERIFIED_SUSPENDED` must not be
minted. If no supported section-byte attestation exists, the exact contract
cannot be implemented on this platform as written; that is a hard boundary,
not permission to rename a weaker file-provenance claim.

## Dependency order

The non-live next slices are an isolation policy/negative-test prototype
with no host mutation, and an independent supported-API feasibility review
for the section-byte measurement. Only after both designs have positive
evidence should separate host-mutation or native-process authorizations be
considered. New custom-provider transport/model IDs and gateway request
identity remain separate downstream work. Production activation stays OFF.

## Primary references

- [AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)
- [CreateProcessAsUserW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessasuserw)
- [WFP ALE connect fields](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/fwpsk/ne-fwpsk-fwps_fields_ale_auth_connect_v4_)
- [PS_CREATE_NOTIFY_INFO](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-_ps_create_notify_info)
- [Load-image notification](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/content/ntddk/nf-ntddk-pssetloadimagenotifyroutine)
- [Section-synchronization parameters](https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/flt-parameters-for-irp-mj-acquire-for-section-synchronization)
- [Executable images](https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/executable-images)
- [CreateFileMappingW SEC_IMAGE](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw)

`PRODUCTION_ACTIVATED=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
