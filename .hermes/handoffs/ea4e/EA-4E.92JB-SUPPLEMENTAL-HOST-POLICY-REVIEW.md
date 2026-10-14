# EA-4E.92JB supplemental Kilo host-policy review

Status: qualified fake-only comparison; START AUTHORITY: NO.
Governing predecessor: `11da09a78e4978ec9885d6ff363b50f2e7d6b542`.

This pure comparison layers proposed effective Docker host settings over the
existing 92IG candidate/image/mount check and the durable 92IJ created-ID
report. It checks a created, nonrunning container with the expected non-root
user; 2 CPUs, 2 GiB memory, 64 PIDs; read-only root, `CapDrop=ALL`,
`no-new-privileges`, no published ports, no auto-remove, and a bounded
`/work` tmpfs. It also checks the exact reported network ID, internal bridge
configuration, and exactly the receiver and gateway member IDs. Every match
returns `HOST_POLICY_REVIEW_ONLY_START_DENIED`.

The focused synthetic suite passed 48 tests across this comparison, the
earlier pre-start checker, and the created-container report. Denials cover
identity, resource, capability, tmpfs, network, and membership drift. No
Docker API, container, receiver, provider, model, or production state was
used or changed.

This is not yet a frozen launch spec. The numeric limits are conservative
proposal values, not demonstrated suitable for real Kilo. The comparison
does not independently fetch daemon state or verify labels, all namespace
and userns modes, ulimits, log driver/rotation, cgroup placement, storage
quota, gateway process identity, or the image-byte strict-profile invariant.
The supplied network membership is not independent socket-owner proof.
Before a container owner can start anything, those effective settings need
an explicit versioned contract, a qualified daemon adapter, and fail-closed
prestart/poststart observation and cleanup. The accepted local-Docker
threat model is separate from strict 92AT, which remains HOLD. Production
remains HOLD.
