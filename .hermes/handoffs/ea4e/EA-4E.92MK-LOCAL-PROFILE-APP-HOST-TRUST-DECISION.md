# EA-4E.92MK local-profile app-host trust decision

Status: OPERATOR-ACCEPTED DESIGN DECISION / NON-LIVE / PRODUCTION HOLD.
Governing source: `780e1646a202fe0167a12c7a9aae0542c1051a2c`.

The operator explicitly chose to trust the current Windows app process and
its account for the accepted 92DE local-container profile. This is a profile
boundary decision, not an observation that the process or its loaded package
was independently protected. A same-account process able to modify the app,
its configuration, or its authority stores is inside the trusted computing
base for this profile. This tradeoff is not hidden behind a hash or SID check.

For this profile only, app-host admission may be specified without the
strict 92ME protected-package observer and independent launcher. It must
be a separately named, explicitly selected path. The existing 92ME native
owner cannot be called with `fake_only=True` and then reported as production
ownership. The 92AT mapped-image-byte requirement and 92CZ administrator-
inclusive threat model remain REJECT/HOLD, unchanged and non-equivalent.

The local-profile app-host path must still bind one named app instance and
authority-store identity/epoch to the request, reject implicit startup and
stale/foreign contexts, and preserve default-disabled activation. It may
not itself issue Docker mutation grants, infer UAC consent, launch a receiver,
or claim a model response. The separate 92JY protected issuer installation
and action-specific one-shot Docker authority remain required. An ordinary
worktree module must never be imported into an elevated issuer.

This decision does not implement app-host admission, install an issuer,
mutate Docker, invoke Codex/Kilo/OpenCode or a model, or activate production.
Next non-live implementation: a versioned local-profile app-host admission
gate and negative tests, isolated from the strict 92ME owner.
