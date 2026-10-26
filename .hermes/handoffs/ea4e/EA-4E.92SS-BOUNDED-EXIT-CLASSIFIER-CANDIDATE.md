# EA-4E.92SS bounded exit classifier candidate

Date: 2026-10-26

The 92SR authorized tags-only run stopped at the post-start `running`
containment check. No server request ran, and the exit reason was not
observed. This source-only successor retains the fail-closed `running`
predicate and exact-owned cleanup. When a previously started container is
observed stopped, it appends only a bounded integer exit code (0 through
255, otherwise `unknown`) and a boolean OOM flag (otherwise `unknown`). It
never emits raw Docker error text, inspect values, or logs.

Focused strict non-live tests passed 48/48, including immediate post-start
exit, no `/api/tags` call, exact cleanup, and malformed state values that
cannot appear in a rendered traceback. No Docker, Ollama, model, GPU,
receiver, or handoff ran for this change. This fake evidence does not
establish native behavior.

The committed candidate requires a new independent source-only review and
then a fresh exact one-shot authorization before any native tags-only
diagnostic. The empty-`manifests-v2` hypothesis remains untested.
Production remains HOLD.
