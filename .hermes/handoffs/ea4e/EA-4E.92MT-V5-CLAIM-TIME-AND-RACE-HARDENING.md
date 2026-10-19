# EA-4E.92MT v5 claim-time and race hardening

Status: NON-LIVE / PRODUCTION HOLD.
Parent: `95f9539d57654d29a78826e227fbacb1ea17a844`.

Review of the 92MS store found that a caller-supplied claim timestamp before
`issued_at` was not denied. The protected grant identity now exposes its
immutable `issued_at`, and **v5 only** denies any state transition whose
supplied time is earlier. The v4 fake-store transition rules are unchanged.

The dedicated tests cover pre-issuance claim/revocation denial and two
concurrent process claims of the same grant. Five additional repeated race
runs each produced exactly one success and one denial. The combined v5/v4
grant, builder, store, identity, request binding, and ceremony ladder passed
127/127 in the working tree.

This does not turn caller-supplied time into a trusted clock. A future issuer
must obtain and bind current time independently, as well as the protected
policy, operator, executable, installation, and store expectations. No
Docker mutation, UAC, receiver/model call, GPU/ComfyUI use, or production
activation occurred. Strict 92AT remains REJECT/HOLD.
