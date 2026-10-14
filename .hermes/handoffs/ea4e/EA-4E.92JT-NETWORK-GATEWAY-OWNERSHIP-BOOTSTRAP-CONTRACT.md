# EA-4E.92JT network and gateway ownership bootstrap contract

Status: NON-LIVE DESIGN / NO OWNERSHIP CLAIM OR DOCKER MUTATION.
Governing source: `80f2e8cc2ab120c62dc8e83b78e94554af7e17b9`.

## Boundary

The 92JR/92JS report can detect drift against caller-provided metadata, but
cannot establish that Hermes created or controls a network or gateway. A
matching Docker inspect, label, name, or SQLite hash alone cannot promote an
arbitrary preexisting object to an owned object. The older inert probes prove
only their own bounded fake runs and do not provide a reusable owner claim for
the 92JC Kilo candidate.

The first real owner sequence must therefore use fresh deterministic object
names under a separately bound, exactly one-shot network-create authority.
The network claim is written durably before Docker mutation. The gateway
requires its own separate create authority, claim, post-create observation,
and start authority/claim; network creation never implies gateway creation or
start. Kilo container creation is a fourth, later budget and remains denied
until the network and gateway owner records are verified in the same current
authority context.

## Required identity and state

Each claim binds the delegated attempt, governing source commit, exact
authorization ID and issuer store identity/epoch, operator identity, object
name and expected labels, Docker endpoint/executable identity, request hash,
TTL, cancellation/revocation state, and predecessor claim hashes. Gateway
claims additionally bind the pinned image index/manifest, exact network ID,
alias, and effective no-port/no-mount policy. Claims are attempt-unique and
object-name-unique in the authority database. `CLAIMED` and `IN_FLIGHT` both
consume the one-shot budget; uncertain outcomes never retry automatically.

After each mutation, the owner records the exact returned Docker ID and
read-only raw inspection bytes. Reconciliation after timeout/crash searches
only the original deterministic name/labels and expected endpoint; zero,
multiple, renamed, foreign, or changed candidates remain HOLD. A result from
the mutation CLI is not itself ownership proof. The gateway must be observed
on the exact claimed network with no foreign members before 92JS can be used
as an additional freshness comparison. Its `MATCH` remains non-authorizing.

## Qualification order

1. Freeze the independent issuer and immutable, one-shot authorization
   artifact for network create, gateway create, gateway start, and Kilo create
   as four separately scoped actions. The existing invocation issuer is not
   automatically a Docker-mutation issuer.
2. Implement the network and gateway claims with atomic conflict/replay,
   expiry/revocation, uncertain-outcome, restart, and exact-ID tests against
   isolated SQLite and fake Docker clients.
3. Qualify a process-tree-contained mutation driver and effective Docker
   setting checks. The current immediate-child inspect runner is not this
   driver.
4. Run bounded, separately authorized real create-only probes in the order
   network, gateway, gateway start, then Kilo create. Every probe needs its
   own committed-source, object, image, budget, cleanup-owner, and audit
   envelope; an earlier fake-probe approval cannot be reused.
5. Only after prestart inspection and later separately governed receiver
   execution may an actual agent-to-agent result path be qualified. No fake
   test result is production activation.

This design does not implement the issuer, owner store, mutation driver, or
live probe. It grants no Docker create/start permission, real receiver/model
execution, or production activation. Production remains HOLD.
