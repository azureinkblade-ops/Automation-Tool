# EA-4E.92IA Linux Ping Plan Complete Binding

Status: NON-LIVE / PURE VERIFICATION / PRODUCTION_READY=NO.

The accepted Linux Kilo ping candidate now includes a digest of its entire
plan, not just argv. `verify_agent_local_kilo_ping_plan` independently
rebuilds it from the accepted start witness and invocation bridge, compares
every field, and rejects a changed image, network setting, launch flag,
permission, identity, or prompt even when a caller recomputes a digest.
Follow-up correction: comparison uses canonical JSON, because Python equality
would otherwise treat a substituted numeric `1` as equal to boolean `true`.

This is a pre-reservation identity check, not a durable intent, Docker
admission, credential qualification, process observation, or launch permit.
The dummy provider, deny-all agent, unresolved config delivery, unresolved
network binding, and `launch_authorized=False` remain unchanged. No real
receiver or model was invoked.
