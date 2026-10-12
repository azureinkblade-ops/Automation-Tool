# EA-4E.92HU Accepted Text Ping Command

Status: NON-LIVE / PURE COMMAND SHAPING / PRODUCTION_READY=NO.

For a deliberately narrow `agent_ping` task with no input files or tool
capabilities, `build_agent_text_ping_command` now derives one fixed text
message from the accepted task-input hash and uses the existing Kilo or
OpenCode argv builder. It checks receiver, receipt, launch, STARTED, and
bridge lineage. The returned argv digest can be reserved and rechecked by
the durable process-intent store. OpenCode requires an explicit trusted
configuration and qualified runtime-binding value; neither builder starts a
process or reads interactive credentials.

Qualification: 5 focused tests and 183 affected tests passed, 0 failed.
Both receivers, changed bridge/task, missing OpenCode binding, and intent
revalidation are covered. The OpenCode test executable is an inert file,
not a receiver. No model, network, Docker, GPU, ComfyUI, or production
activation occurred.

This does not verify the actual executable bytes, model selection,
credential or egress policy, process start, or terminal-byte provenance.
The delegated ping's network-deny test scope is a fake-only contract, not
authority for a provider call. A trusted process owner and separately
authorized bounded live qualification remain required.
