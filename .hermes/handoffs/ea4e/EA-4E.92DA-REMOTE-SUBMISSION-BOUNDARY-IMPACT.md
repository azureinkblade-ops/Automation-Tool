# EA-4E.92DA remote submission boundary impact

Status: SOURCE-ONLY REVIEW / REMOTE EXECUTION NOT QUALIFIED
Baseline: `f3d507a22e5075f0f40edc9fa740f05e4ad18750`

The 92CZ administrator-inclusive decision makes the present Windows PC an
untrusted client for any future independently administered execution host.
This review traces the current application path without changing it.

## Current local path

`app.py` registers `POST /api/governed-production-action` and passes its JSON
body to `submit_governed_production_action`. The configured lifecycle owner
ultimately uses `ProductionAppHostAction`, which reconstructs a caller-
supplied execution authority, activation artifact, and invocation issue
request. The `GovernedProductionCaller` checks request/receiver identity and
passes the issue request to `ProductionInvocationAuthorizationIssuer`.
That issuer validates the resolved binding, TTL, attempt number, scope,
and durable-store identity before persisting an authorization. The lifecycle
adds request-scoped activation-authorization checks. None of this means a
network caller is an independently verified operator.

The app composition is default-disabled: without explicit configuration,
the HTTP path returns `MISSING_GOVERNED_ACTION_DEPENDENCY`. Existing fake
tests verify that missing governance artifacts, mismatched receivers, and
disabled activation deny execution. This review does not claim those tests
prove the route safe to expose to an administrator-controlled remote client.

## Required separation for a remote host

Do not expose the present `app.py` action or its issuer directly as the
remote submission API. Its caller-provided `production_activation_explicit`
Boolean and reconstructed artifacts are not independent remote approval.
A local administrator can also control local app process, files, and
network client, so local evidence cannot attest approval to the remote host.

A remote submission endpoint must accept only an inert canonical proposal:
task content/hash, requested receiver, and an idempotency key. It must have
no reference to issuer, binding controller, activation policy, durable
authorization store, execution boundary, or gateway send path. Receipt is
`PENDING_REVIEW`, not `AUTHORIZED` or `EXECUTING`. The remote host's own
independently authenticated operator workflow must decide whether to issue
the exact authority and must bind that decision to the proposal hash,
receiver/source identity, scope, TTL, one-attempt budget, and remote audit.
Authentication credentials or an approval click controlled solely by this
untrusted PC do not satisfy that boundary.

Before implementation, freeze the remote authority owner and approval
channel, then write fake-only tests proving submission alone cannot call
issuer, activation, bind, executor, or model; malformed/replayed proposals
cannot mutate stores; and only a separate remote-side approval can advance
the state. The existing local action remains unchanged and default-disabled.

## Focused verification

Against baseline `f3d507a22e5075f0f40edc9fa740f05e4ad18750`,
`py -3.14 -m pytest -q -p no:cacheprovider
tests/hermes_core/test_ea4e52_nonlive_app_host_integration.py` passed
27/27. The suite uses injected fake executors; its HTTP-handler test does
not open a listener. This verifies current local default-deny and fake
configured-dispatch behavior, not remote approval or live safety.

This is an architecture gap, not an observed bypass of the current local
governance checks. No remote host exists in this checkpoint, and no network
request, receiver, provider, model, or native proof process ran.

The independent exact 92AT mapped-image-byte requirement remains
REJECT/HOLD. A remote-submission design does not satisfy it.

`REMOTE_SUBMISSION_BOUNDARY_IMPLEMENTED=NO`
`REMOTE_OPERATOR_APPROVAL_QUALIFIED=NO`
`PRODUCTION_ACTIVATED=NO`
