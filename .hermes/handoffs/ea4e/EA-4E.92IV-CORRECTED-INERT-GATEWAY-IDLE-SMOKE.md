# EA-4E.92IV corrected inert gateway idle smoke

Status: PASS for isolated gateway startup and idle expiry only.
Source HEAD at run: `28eb5fe72a6b474c064cf11a36e632f1b1b58714`.
Image index: `sha256:afdd2f974bb91d8b3c9bc8da6dd2ac4c2667d4fe1c4e756b0e818e9eff5cd511`.
Image source label: `7c78d484e2c3a334570bcbb21866f86db599332f`.

The operator separately approved one corrected inert gateway-container
smoke after 92IU's combined inspect gate denied. Before starting, the
command created exactly one container and printed each selected inspect
field. Its exact ID was
`17b60432370a547d1714026d3d28a5e34f67e1ed28fe00b4fef83d9db2432a23`.
The Docker container `Image` and `Config.Image` fields both equaled the
pinned image-index digest above. The pre-start record also showed:

```ini
network=none
readonly_root=true
mounts=0
port_bindings=0
cap_drop=ALL
security_opt=no-new-privileges
running_before_start=false
prestart_policy=PASS
```

The run used the fake-only marker, synthetic attempt/task/receipt hashes,
and a synthetic task-bound SSE response. It published no port and had no
network or mount. After the passing pre-start check, that same container
started once and exited within the 25-second host deadline with code `2`.
This is consistent with the gateway's no-request idle-expiry path; the
container had no request path and no release signal. Bounded Docker
logs contained zero lines. The `finally` block removed the exact ID;
subsequent read-only queries by ID and candidate-image ancestry returned no
containers. There was no request, signal-based release, Kilo/OpenCode
receiver, model, GPU/ComfyUI, or production activation.

The 92IU failed predicate remains unproven: its removed inspect fields were
not retained. This run demonstrates that the corrected field-by-field gate
accepts the observed image/index and isolation settings, but it does not
prove why 92IU denied. It also does not prove request-body compatibility,
Docker network/peer attribution, durable release authority, result return,
or a working agent-to-agent handoff. Strict 92AT mapped-byte proof remains
HOLD under its original threat model. Production readiness remains HOLD.
