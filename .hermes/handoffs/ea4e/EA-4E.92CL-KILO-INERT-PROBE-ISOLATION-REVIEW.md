# EA-4E.92CL Kilo inert-probe isolation review

Status: NON-LIVE REVIEW / KILO PROCESS LAUNCH HOLD
Source checkpoint: `d1a24d1b94afa4e095d41e06ea8b6b75d4ab691f`

The 92CK probe has a fresh credential-free home, a pinned Kilo binary,
an inert custom model, and a loopback fake provider. These controls do not
stop the Kilo executable from making unrelated outbound connections. A
dummy provider key and an isolated home are not network isolation.

## Read-only host checks

- `C:\Windows\System32\WindowsSandbox.exe` was absent. The Windows Sandbox
  optional-feature state could not be read without elevation; absence of the
  launcher is not proof the feature can never be enabled.
- Docker CLI was installed, but its Linux-engine named pipe was unavailable.
  A Linux container is not a qualification of this pinned Windows executable.
- `vmcompute` was running, but that alone does not establish a usable
  network-disabled Windows VM or container.
- No matching active program-specific firewall rule was returned for the
  pinned `kilo.exe`. This does not establish that all egress is allowed or
  blocked; other host policy may exist.
- No firewall, virtualization, network, or credential setting was changed.
  No Kilo process or model was invoked.

## Safest next action

Use a disposable Windows VM or Windows Sandbox with external networking
disabled. Put the fake HTTP provider and Kilo process inside that same
isolated environment so loopback still works. Import only the hash-verified
executable, probe code, and fresh dummy config; do not import the user's
production Kilo home or auth state. Before launch, prove the VM has no
external route, record the exact executable/config hashes and one-process
limits, and obtain a separate exact inert-receiver authorization.

Do not create a broad firewall rule against the existing Kilo executable:
it could disrupt unrelated VS Code or app workflows, and a path-only rule
does not by itself cover child processes or alternate network paths.
Do not mark the launch plan's `network_isolation_verified` flag true based
on a config value or a successful local fake-provider test. It requires
host-level evidence from the actual isolated execution environment.

Until that environment exists and is verified, the probe remains prepared
but not launchable. The custom-provider probe would not qualify the unchanged
production Kilo route; the separate EA-4E.92S mapped-byte HOLD also remains.
