# EA-4E.92EN Two-Stage Network Binding Qualification

Status: non-live source qualification only; no new probe authorized.

The 92EM diagnostic showed that Docker inspect reports `NetworkID=""` for
both never-started helpers, despite the intended named network attachment.
The created-state checker now permits only the empty string or the exact
created network ID in that field. It still requires the exact sole network
attachment name, named `HostConfig.NetworkMode`, internal bridge network,
labels, container configuration, no mounts/ports/GPU, and no foreign member.
A missing, null, or wrong nonempty network ID remains denied. A created-state
match remains metadata-only; it does not establish the runtime binding.

The running-state observation is unchanged: it requires each endpoint's
`NetworkID` to equal the exact network ID, matching network member IPs,
running states, no published ports, and the held-open socket peer comparison
before the coordinator can send its one release signal. A new regression
asserts that a blank running `NetworkID` is denied.

Focused fake-only ladder: 96 passed, 0 failed. No Docker command was invoked
by these tests. The 92EL one-shot diagnostic approval was consumed by 92EM;
this checkpoint does not grant a rerun or any Kilo/OpenCode/model/production
authority. Exact mapped-byte proof remains REJECT; production remains HOLD.
