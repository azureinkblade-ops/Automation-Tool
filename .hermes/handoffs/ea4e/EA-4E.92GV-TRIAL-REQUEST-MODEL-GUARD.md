# EA-4E.92GV Trial Request-Model Guard

Status: NON-LIVE SOURCE CORRECTION. Parent: EA-4E.92GU.

The canonical 92GS binding permits `model_id` and `request_model_id` to
differ. The 92GU pre-claim synthetic-task check initially used `model_id`,
while the provider boundary used the actual request model. This could
consume a one-shot credit for a different task even though forwarding would
still fail closed. The pre-claim check now uses `request_model_id`.

A fake-only regression binds a different configured model to the Nemotron
trial request model and verifies that a non-synthetic task is denied before
claim, receiver start, or capture-directory creation. The bounded
artifact/store/SSE/capture/binding ladder passed 183 tests with zero
failures; `git diff --check` passed. No real OpenCode process, provider,
model, GPU, or production activation was invoked. The separate trusted
issuer, credential, enforced egress, process accounting, and live-proof
gates remain open. `PRODUCTION_READINESS=HOLD`.
