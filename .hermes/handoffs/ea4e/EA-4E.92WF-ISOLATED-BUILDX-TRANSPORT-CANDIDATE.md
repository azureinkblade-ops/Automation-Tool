# EA-4E.92WF Isolated Buildx transport candidate

Date: 2026-10-31 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW AND NATIVE RUN HOLD

The existing 92RM Docker CLI transport now has a non-default isolated
`buildx inspect default` mode. It requires the exact 92WC layout type,
disallows the older user-config mode and every other command or stdin payload,
revalidates the empty config and one-plugin tree immediately before and after
the process, supplies only `SYSTEMROOT`, `DOCKER_CONFIG`, and the fake
`ProgramFiles`, sets the checked config as cwd, and retains the explicit local
npipe host. On success it denies duplicate fields, non-UTF-8 output, a
non-`docker` driver, or an endpoint other than the exact npipe; it returns only
`local_default_docker`, never raw builder output. Ordinary Docker invocations
retain their previous environment and working-directory behavior.

Focused synthetic checks plus the existing fake-only 92RM suite passed:
111 tests total on staged-identical worktree source, with the repo live-test
setup excluded. These tests do not prove a native builder, successful endpoint
format, or production readiness. The Docker Desktop UI previously displayed
the endpoint label `default`, so the strict parser may deny the real output;
that is an intentional fail-closed result until local identity is proven.

This candidate still lacks a reviewed private setup/ACL, a lock against plugin
replacement during launch, process-tree containment, and a proven hard wall
deadline including hashing and cleanup. The 92VZ standalone probe remains on
HOLD. No private plugin copy or native Docker/Buildx call was made. No
container, archive upload, build, model, GPU, receiver, handoff, or production
action ran. The private model archive and preserved Docker runtime directories
remain untouched. Independent source review and separate exact native
authorization are required; all production gates HOLD.
