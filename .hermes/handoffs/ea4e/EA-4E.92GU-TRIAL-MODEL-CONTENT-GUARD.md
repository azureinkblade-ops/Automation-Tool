# EA-4E.92GU Trial-Model Content Guard

Status: NON-LIVE SOURCE CHECKPOINT. Parent: EA-4E.92GT. No real receiver,
provider call, credential transfer, issuer, or production activation.

The 92GQ capture boundary previously classified a provider request as a
task call if it contained the authorized task as a substring. A request
could therefore also carry additional messages or parameters. An in-process
no-network check reproduced this: a two-message request classified as
`TASK_CALL`. That is insufficient for the published trial-only data rule
for `opencode/nemotron-3-ultra-free`.

For that model only, admission now requires the exact frozen synthetic task
before claim. The cooperative provider boundary forwards only the minimal
single-user-message request containing that task, with no extra fields or
messages. Additional content is classified `UNAPPROVED_TRIAL_CONTENT` and
never reaches the injected upstream. Existing `AUXILIARY_NON_TASK` behavior
and all other models' request classification remain unchanged. Denial after
claim consumes the one-shot credit and fails the capture closed.

Four new cases cover another fully authorized task, an extra message, an
extra request parameter, and task text with appended content. The bounded
fake-only artifact/store/SSE/capture/binding ladder passed 182 tests with
zero failures; `git diff --check` passed. No installed OpenCode process or
model was invoked.

This guard constrains only the injected cooperative path. It does not prove
that a real SDK request has this shape, prevent a receiver from bypassing the
boundary, enforce OS-level egress, prove a Zen credential, or make the trial
endpoint suitable for confidential production tasks. A real SDK request
with additional system text must fail until it is separately reviewed and
the contract is revised under a new data-use decision. Production readiness
remains HOLD.
