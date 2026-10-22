# EA-4E.92QJ Inert Close Fault Injection

The 92QI independent review accepted the narrow cleanup/reconciliation
correction at source level and requested an inert throwing-close check. This
checkpoint compiles the unchanged unwired owner with test-only dependencies.
The fake native adapter returns a synthetic non-sentinel value; the fake
wrapper takes ownership immediately, so the owner's Win32 `CloseHandle`
import is never invoked. The fake wrapper throws from `Dispose()` once.

Two modes exercise the actual owner control flow: a shape denial leaves the
handle in `owned`; a synthetic `Inspect` denial after a successful observer
leaves it in `accepted`. Both return the primary
`DENY:POST_ATTEMPT_RECONCILIATION_REQUIRED`, keep the specific observation,
mark `DENY:WRAPPER_CLOSE_UNCERTAIN`, preserve partial identity, retain no
handle, and record exactly one fake create call and one disposal attempt.
A separate source-order assertion checks that raw-close uncertainty is set
before `CloseHandle` and cleared only after the call.

Focused tests passed 3/3; the adjacent inert matrix passed 116/116 before
staging. This is control-flow evidence, not a valid Windows handle, native
close-failure observation, ACL/effective-rights proof, or production
qualification. In particular, a raw `CloseHandle` throw was not dynamically
injected because the owner has no inert raw-close injection point; the test
does not invoke that import. The production owner source is unchanged.

The full source owner and native issuer remain HOLD. Strict 92AT mapped-byte
proof remains REJECT. No native owner, Docker mutation, Kilo/OpenCode/model,
GPU, ComfyUI, or production action occurred.
