# EA-4E.92WO isolated Buildx cooperative deadline

Status: SOURCE-LEVEL DEADLINE ACCOUNTING / NATIVE LAUNCHER HOLD.

The isolated Buildx invocation now starts its deadline before layout
validation. Path and directory checks and plugin hashing check that same
deadline between operations; the CLI launch is denied if validation consumes
the budget. The post-call layout check uses the original deadline. Ordinary
Docker transport timeout placement is unchanged.

Focused synthetic tests cover pre-read expiry, expiry during plugin hashing,
launch denial after the layout spends the budget, and pre/post deadline
identity. These are cooperative checks: they cannot interrupt a blocked
filesystem operation, guarantee a hard wall clock, contain a Buildx child,
hold the plugin executable identity through load, or independently prove
builder/daemon locality. Windows Job Objects can manage associated process
trees, but the current `DockerCli` does not use a qualified creation-time job
binding: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects

No Docker, Buildx, model, GPU, receiver, handoff, or production action ran.
Native and production gates remain HOLD.
