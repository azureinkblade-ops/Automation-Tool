# EA-4E.92WG Isolated Buildx transport review hold

Date: 2026-11-02 (America/Phoenix)
Status: INDEPENDENT READ-ONLY REVIEW HOLD / NO NATIVE RUN

David authorized one independent read-only review of committed 92WF source at
`2b547ce8e2994a8f861d837422b9c68527df9801`. The reviewer inspected
committed source and synthetic tests only and returned HOLD for native use.
The one-review authorization is consumed. No tests or executables ran in the
review.

Findings:
- `DockerCli` kills the CLI process, not a Buildx child process. Layout
  hashing precedes the deadline and cleanup waits can exceed it
  (`tools/ea4e92rm_container_smoke.py:171,250`;
  `tools/ea4e92wc_isolated_buildx_layout.py:59`).
- Directory checks and the plugin hash are snapshots. No lock or retained
  executable handle prevents replacement before Buildx loads the plugin;
  post-call validation cannot undo execution
  (`tools/ea4e92wc_isolated_buildx_layout.py:81`;
  `tools/ea4e92rm_container_smoke.py:171`).
- A matching endpoint output string is not independent proof of the local
  builder or daemon used. The parser ignores other lines, and success tests
  provide a synthetic response (`tools/ea4e92rm_container_smoke.py:295`;
  `tests/hermes_core/test_ea4e92wf_isolated_buildx_transport.py:48`).
- `SYSTEMROOT` is inherited from the caller and subprocess-start exceptions
  are not converted to fixed categories, leaving isolation and redaction
  incomplete (`tools/ea4e92wc_isolated_buildx_layout.py:90`;
  `tools/ea4e92rm_container_smoke.py:196`).

The reviewer found no apparent change to ordinary Docker invocations'
environment or working directory. Fake tests do not prove Windows ACLs,
native Buildx output, or production readiness. Private plugin setup, Docker,
Buildx, container, build, model, GPU, receiver, handoff, and production
actions remain HOLD. The private model archive and preserved Docker runtime
directories were untouched. A corrected source path needs focused tests,
new independent review, and separate exact native authorization.
