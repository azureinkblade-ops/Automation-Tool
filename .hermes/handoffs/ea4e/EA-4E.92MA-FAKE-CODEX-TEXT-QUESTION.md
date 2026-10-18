# EA-4E.92MA fake Codex text question

Status: NON-LIVE / PURE STDIN PROMPT + FAKE REGISTRY / PRODUCTION HOLD.
Baseline: `8411a5d3ca15e481245133299578f0ad7d92713b`.

Codex now has a pure text-question stdin plan for the same bounded
`agent_text` task and `hermes.agent_text_result/v1` schema as the
Kilo/OpenCode command candidate. It requires no tools, file paths,
network, redelegation, inputs, or extra instructions and a maximum
60-second task/lease budget. The prompt binds the task input and accepted
receipt hashes. A fake persisted Codex terminal record is then recovered
through the 92LW/LX text-return path; after store restart the originator
receives and acknowledges one result. Changed task/scope and receiver
substitution are denied.
The focused Codex plus Kilo/OpenCode matrix passed 10/10. The adjacent
text-return, command, ping, lineage, terminal-capture, and result-store
ladder passed 164 tests plus 6 subtests, zero failures.

The prompt hash is not an invocation authorization or a proof of actual
Codex stdin bytes. No CLI process or model ran. The result text was
test-authored, not model-authored. Real output compatibility and the
protected app/issuer, installed dependency closure, and bounded live
qualification remain open. The local-Docker route is still unqualified;
the strict Windows 92AT route remains REJECT/HOLD.
