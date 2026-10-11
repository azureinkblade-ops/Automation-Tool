# EA-4E.92GZ Result Host Configuration Guard

Status: NON-LIVE / FAKE-ONLY. Parent: EA-4E.92GY.

The explicit `AgentPingRecoveryHost` now rejects absent, wrong-type, and
mismatched authority, start, capture, registry, or result dependencies when
configured. Previously, a mismatched set could be installed in `app.py` and
would fail only on a later recovery call. Configuration remains default-disabled
and does not start a receiver or expose a route.

Focused qualification:

`test_ea4e92gp_agent_ping_recovery_host.py`,
`test_ea4e92gy_app_agent_ping_recovery.py`,
`test_ea4e92gn_agent_ping_recovery.py`, and
`test_ea4e92gh_terminal_capture.py`: 25 passed, 0 failed.

The existing `app.py` invalid-escape deprecation warning remains unrelated.
No real agent, model, Docker, GPU, or production activation was invoked.
The process-to-durable-capture owner and separately governed live qualification
remain open. `PRODUCTION_READY=NO`.
