# EA-4E.92KV external store-identity binding

Status: NON-LIVE / FAKE-ONLY BINDING QUALIFIED. Not a protected issuer.
Baseline: `123d085b8fbd27360d62ad2f1afcbca6349695bf`.

`Ea4eNetworkGrantV4Store.OpenExpected` opens and verifies the complete v4
database/journal/anchor set, then compares its store ID and epoch against
independently supplied expected values. It disposes the handle on mismatch.
The fake issue probe now uses this path; valid but foreign store identity or
epoch is denied. This removes one store-substitution path but does not prove
the caller's expected values are trustworthy.

Focused v4-store/builder tests: 29 passed, 0 failed.
Adjacent EA-4E.92I/J/K and HJ/HV/HY fake-only tests: 552 passed, 0 failed.
No Docker, receiver, model, GPU, ComfyUI, or production activation occurred.

Source audit: `production_app_host.py` constructs `DispatchAuthority` from an
incoming mapping; `receiver_dispatch.py` verifies a hash over that mapping's
own artifact fields. Neither is an independent operator approval witness or
current Docker-mutation authority. The expected store identity, current
authority, operator SID, trusted clock, and approved grant fields must be
bound by a separately protected ceremony source and reviewed installation.
The prior 92KM binary predates v4 and cannot be promoted. Production HOLD.
