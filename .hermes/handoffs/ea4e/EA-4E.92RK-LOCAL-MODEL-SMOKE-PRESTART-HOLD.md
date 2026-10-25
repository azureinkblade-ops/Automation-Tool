# EA-4E.92RK Local Model Smoke Prestart Hold

Status: APPROVED ONE-SHOT SMOKE NOT STARTED / PROCESS AND EGRESS HOLD.
Source baseline: `96214efad1ba72aa5ab3738dbe5228ea2ebbfd0e`.

David approved one bounded synthetic local-model smoke: the recorded Ollama
executable and `qwen3:14b` files, one localhost inference request, no private
data, a 120-second deadline, exact-process cleanup, and possible GPU use.
The approval expressly required stopping if process or cleanup bounds could
not be enforced. It did not authorize OpenCode, Kilo, inter-agent delivery,
or production activation.

Prestart review found that `tools/ea4e92cm_kilo_inert_runner.py` creates a
child with `subprocess.Popen` and only then assigns it to a Windows Job.
There is a process-start-to-assignment interval in which the job limit and
kill-on-close cleanup are not yet enforced. Its one-process limit also does
not establish that an Ollama server and its model runner would function.
The EA-4E.92S suspended-process and AppContainer modules are explicitly
test-owned or partial; they are not a qualified native Ollama launcher.
No reviewed localhost-only egress control is present for the proposed run.

Therefore no Ollama process, inference request, OpenCode/Kilo receiver, or
GPU task was started. The approved run budget was unused, but this approval
is not a standing grant for a changed launcher or execution envelope.

Next non-live gate: qualify an owner that creates the process suspended
with a job bound at creation, verifies membership before resume, enforces
the wall-clock and cleanup bounds, and proves the exact localhost-only
egress policy without changing unrelated host state. Pin and review that
owner and the model/runtime identities before requesting a new exact live
authorization. Do not treat a fake-only supervisor test as native proof.
Production remains HOLD.
