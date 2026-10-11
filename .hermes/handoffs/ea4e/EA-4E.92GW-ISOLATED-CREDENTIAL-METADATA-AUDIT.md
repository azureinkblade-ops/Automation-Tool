# EA-4E.92GW Isolated OpenCode Credential Metadata Audit

Status: READ-ONLY NON-LIVE AUDIT. Parent: EA-4E.92GV. No credential values,
provider requests, receiver processes, or production activation were used.

The isolated EA-4E OpenCode state database exists, but a read-only metadata
query found zero rows in `account` and zero rows in `credential`. The
isolated home has no `.local/share/opencode/auth.json`. Its config still
selects `ollama/qwen3:14b` and defines only the `ollama` provider. The
separate interactive auth file was not copied; a previous key-name-only
inspection found `openai`, not `opencode`, at its top level. Neither state
is evidence of an isolated OpenCode Zen credential.

`ProductionCredentialReadinessPreflight` is explicitly structural. For its
OpenCode policy it confirms that the configured state-file path is under
the allowed root and has at least one byte. It does not inspect provider
entries, authenticate, or prove that a hosted model can be used. Its
`ready=True` result must not be promoted into Zen credential readiness.

The next credential phase needs an explicit, approved reference or broker
for the chosen existing account, provider-specific non-secret readiness
evidence, and a verified effective config. It must not copy secrets into
the repository, the isolated runtime, or a capture manifest by default.
No live probe may infer authorization from this audit.

`ISOLATED_ZEN_CREDENTIAL_PROVEN=NO`; `PRODUCTION_READINESS=HOLD`.
