# EA-4E.92CW Windows host isolation feasibility

Status: READ-ONLY HOST REVIEW / PRODUCTION PEER ISOLATION HOLD
Baseline: `dde3bada8c68b88eb50e2597608126282ff147f9`

## Observed host

Read-only OS inventory reports Microsoft Windows 11 Home, build 26200.
The optional-feature query for Windows Sandbox required elevation and did
not return its state. Microsoft documents Windows Sandbox as unsupported
on Home, so it is not a qualified deployment assumption for this host.
No feature, account, firewall rule, AppContainer profile, loopback exception,
or system setting was created or changed in this review.

## Isolation candidates and gaps

- **Windows Sandbox:** not a supported Home-edition feature. Even on a
  supported edition, its loopback/network route to a host gateway would
  need its own exact design and qualification.
- **AppContainer:** Windows documents process, file, credential, and network
  restrictions. But packaged-app loopback is blocked by default; enabling
  a loopback exception for debugging is not evidence that only the intended
  Kilo process can consume a host gateway's HTTP request. Kilo 7.8.3 has
  not been shown to start and use its OpenAI-compatible provider inside an
  AppContainer on this host. No AppContainer token, profile, or exception is
  qualified here.
- **Separate local identity:** Windows can start a process under another
  account, but that requires an account/credential owner, executable and
  profile ACLs, a gateway access design, and a threat model for privileged
  local processes. No dedicated identity for this gateway was identified,
  provisioned, or tested in this review. Merely moving the child to a
  different account is not proof of the HTTP caller under the current
  loopback bearer design.

Under the conservative working model that other same-user processes are
untrusted, none of these candidates currently closes the 92CT peer-identity
gap. A local token plus one-use budget limits replay but cannot prove Kilo
was first to present it. The choice of local adversary model remains with
the operator; this review does not infer approval to trust same-user code.

## Next qualification gate

Select one concrete OS-enforced receiver boundary and prove, with negative
tests on this host, that unrelated same-user processes cannot obtain the
attempt token or consume the sole gateway send. Also prove Kilo can make
only the permitted local connection while the upstream credential remains
gateway-only. This requires a separately reviewed implementation and any
host-setting authorization. Until then, production gateway peer identity
is HOLD. The independent 92S exact mapped-byte requirement is also HOLD.
No real receiver, provider, model, GPU, or ComfyUI operation is authorized.

## Primary references

- [Windows Sandbox](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/)
- [AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)
- [Windows interprocess communication and loopback](https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication)
- [CreateProcessWithLogonW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createprocesswithlogonw)
