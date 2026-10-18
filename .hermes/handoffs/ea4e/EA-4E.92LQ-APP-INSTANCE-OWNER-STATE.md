# EA-4E.92LQ app-instance owner state

Status: NON-LIVE IN-MEMORY CANDIDATE / PRODUCTION HOLD.
Baseline: `80825d1327c38d8945413a9c1ea75ec0a6acf7ea`.

`AppInstanceOwner` retains one receipt returned by an injected launcher.
It accepts canonical launcher/package/instance identities and positive
process handle/ID values, denies a second launch in every state, and
withholds the receipt until a fresh collaborator observation exactly
matches the retained handle, PID, nonce, package digest, and live state.
Exit moves to `EXITED`; only then may the collaborator close that exact
handle. An exception, malformed receipt, drift, or unconfirmed close moves
to `UNKNOWN` and cannot be retried automatically. A new owner object is
required for a new app instance.

The module contains no native process launch, PID lookup, process
termination, shell, network, Docker, issuer, receiver, or model capability.
Its collaborator is fake in the tests. A caller able to substitute that
collaborator or forge its results can fabricate a receipt, so this module
alone is NOT an authority witness. It does not globally serialize multiple
owner objects, prove an executable/package byte closure, prevent a native
handle from being closed elsewhere, or bind the two currently observed
`app.py` process candidates. Those conditions belong to a separately
trusted native launcher and operator-controlled lifecycle.

Focused: `python -m pytest -q -p no:cacheprovider --basetemp=output/ea4e92lq-focused-r2-20261018 tests/hermes_core/test_ea4e92lq_app_instance_owner.py`

Result: 22 passed, 0 failed.

Adjacent fake/native read-only gate: `python -m pytest -q -p no:cacheprovider --basetemp=output/ea4e92lq-adjacent-20261018 tests/hermes_core/test_ea4e92lq_app_instance_owner.py tests/hermes_core/test_ea4e92s_suspended_process.py tests/hermes_core/test_ea4e92y_retained_handle_registry.py tests/hermes_core/test_ea4e92lg_pipe_client_process.py tests/hermes_core/test_ea4e92lj_pipe_client_binding.py`

Result: 101 passed, 0 failed. No staged-only or committed-tree result
is claimed for this WIP yet.

Next: source-review and qualify the independently trusted launcher that
owns the actual process handle and exact package closure. Only after that
can 92LJ's pipe client observation be compared to a real app instance.
No app or protected pipe was launched, no UAC prompt occurred, and no
Docker, Kilo/OpenCode/model, GPU/ComfyUI, or production activation
occurred. Production remains HOLD.
