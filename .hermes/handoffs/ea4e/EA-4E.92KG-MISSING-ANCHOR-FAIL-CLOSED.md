# EA-4E.92KG missing-anchor fail-closed qualification

Status: NON-LIVE / FAKE-ONLY TEST EVIDENCE.
Governing source: `aa2864b387ac5a229027c5971081cb0c1b1c91c2`.

Two isolated tests model an anchor becoming unavailable after a completed
fake issue or claim, preserving the displaced file under a different test
name. In both cases SQLite retains the advanced generation and grant state,
but `Open` denies the incomplete anchor namespace and no issue or claim can
be retried through the candidate. The claim state remains `CLAIMED` rather
than returning to `ISSUED`.

An initial test tried to obstruct the next anchor before the transition.
The store's pre-transition anchor check correctly denied the operation
before SQLite commit, so that setup did **not** exercise a post-commit gap.
The revised tests cover a missing anchor after a completed transition;
they do not inject an actual process crash between SQLite commit and
`WriteAnchor`. A separate, reviewed recovery protocol is still required.

Focused 92KE tests passed 20/20. Adjacent and committed-tree verification
remain required. No production grant, UAC, Docker mutation, receiver/model
execution, GPU, ComfyUI, or activation occurred. Production remains HOLD.
