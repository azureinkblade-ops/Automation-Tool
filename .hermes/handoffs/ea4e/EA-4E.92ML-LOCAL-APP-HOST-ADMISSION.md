# EA-4E.92ML local-profile app-host admission

Status: NON-LIVE CANDIDATE / PRODUCTION HOLD.
Parent: `780e1646a202fe0167a12c7a9aae0542c1051a2c`.
Decision dependency: EA-4E.92MK, accepted local-container profile only.

`tools/hermes_core/local_container_app_host_admission.py` adds a pure,
default-disabled context comparator. A matching request must name the
versioned profile, canonical app/store UUIDs, positive store generation,
40-character governing commit, and the configured current account SID.
Injected read-only observers must return that account SID and store
identity/generation. Missing, malformed, foreign, stale, rolled-back, or
unavailable observations deny. A Python boolean cannot substitute for a
numeric store generation. The only positive reason is
`LOCAL_PROFILE_CONTEXT_ONLY`; it is not an execution authorization.

The governing commit is a configured expected value, not independent proof
of the loaded app's source or mapped image bytes. Tests use fake readers.
This gate does not install or operate the protected Docker issuer, check
actual UAC consent, bind a real activation token, launch a receiver, call a
model, or activate production. It is not the strict 92AT/92ME path. The
current app host remains outside this new gate until a separate integration
and review qualify the call site and its real observation readers.

Focused and adjacent non-live test command:

`python -m pytest -q -p no:cacheprovider --basetemp=output/ea4e92ml-adjacent tests/hermes_core/test_ea4e92ml_local_app_host_admission.py tests/hermes_core/test_ea4e92lq_app_instance_owner.py tests/hermes_core/test_ea4e92mf_app_package_inventory.py tests/hermes_core/test_ea4e92mj_app_agent_text_recovery.py`

Result: 90 passed, 0 failed. No receiver/model, Docker mutation, GPU, or
ComfyUI activity. Production readiness remains HOLD.
