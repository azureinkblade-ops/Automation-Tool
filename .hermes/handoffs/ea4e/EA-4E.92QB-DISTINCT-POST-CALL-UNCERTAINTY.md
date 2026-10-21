# EA-4E.92QB Distinct Post-Call Uncertainty

This non-live source correction responds to the independent 92QA HOLD.
The unwired directory owner now distinguishes pre-call unavailable,
post-call uncertain, and raw-handle-close uncertain denials. The captured
native last error is copied to the output in `finally`, including a denied
post-call path; zero is not interpreted as native success. A failed raw close
still cannot be repaired or adopted by path and requires separately governed
operator reconciliation if a native attempt is ever authorized.

The inert fixture exercises only the pure classifier and pre-call screen. It
never invokes `CreateDirectory2W` or `CloseHandle`. Focused inert/ABI tests
passed 15/15; adjacent unique non-live matrix passed 84/84 before staging.
This is not an independent acceptance of 92QB and does not qualify native
runtime behavior, authenticated issuer inputs, effective rights, a live
receiver/model response, or production. Strict 92AT remains REJECT.
