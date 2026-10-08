# EA-4E.92FF Gateway Identity Diagnostic Remediation

Status: FAKE-ONLY FIELD DIAGNOSTICS PASS / NEW ONE-SHOT HOLD
Baseline before this change: `6000d23f0c73324e94616ae83d91ddc9a9917507`
Date: 2026-10-08 (America/Phoenix)

The 92FE `gateway identity denied` bucket is now separated into returned ID,
name, image ID, and record-shape denials. Only a canonical 64-hex `sha256:`
image ID may appear in an image-mismatch reason; arbitrary inspect content is
not echoed. No identity acceptance condition was relaxed. The 92FE historical
cause remains unknown until a fresh diagnostic reports a specific field.

25 focused created/driver/coordinator fake tests passed with zero failures,
including each distinct identity denial. No Docker object was created or
started for this remediation. The 92FE one-shot remains consumed; a new
bounded never-started diagnostic requires a fresh authorization and must
still clean exact owned IDs. Even a created-state match cannot prove running
socket peer identity or production readiness.

`FIELD_SPECIFIC_DENIALS=PASS_FAKE_ONLY`
`ACCEPTANCE_RELAXED=NO`
`NEW_DIAGNOSTIC_EXECUTED=NO`
`CONTAINERS_STARTED=0`
`PRODUCTION_READY=NO`
