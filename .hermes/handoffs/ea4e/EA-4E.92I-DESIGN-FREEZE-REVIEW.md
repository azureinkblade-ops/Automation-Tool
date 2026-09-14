# EA-4E.92I Design Freeze Review

Result: DESIGN REVIEW PASS / TWO-DOCUMENT CONTRACT AND PLAN FROZEN.
Parent baseline: e74c1518cf38d045824fee89df16cd088dce146c.
Three-file governance checkpoint only; no production/test source changed.

## Frozen Document Boundary

Git-blob/export byte SHA-256, not Windows working-copy newline hashes:
EA-4E.92I-VERSIONED-OPENCODE-BINDING-DESIGN.md:
2a60727fa241c6b7d1ce784c1acc4e8bfb9f8393c779abcce95ea45d3f5a22ab.
EA-4E.92I-DEPENDENCY-AWARE-BINDING-ROLL-PLAN.md:
7a952b133d397e6f24ea9a48a1b60ccea75c8460e809ca2154198e0c1bf911d3.
Both paths are under .hermes/handoffs/ea4e. This review is outside its own
hash manifest, avoiding a self-reference. Adding it does not alter either blob.

## Review Corrections

Freeze exact recursive field sets, types and policy constants; limits 1..65536,
canonical decimal ports and strict Windows path form. Invalid mutated material
cannot be admitted merely because it has a computed hash.
Separate pure contract freeze from actual SDK compatibility: live deployment
must still deny unqualified streaming/routes/multiple calls. No claim that the
current OpenCode SDK meets this fixture's request shape.

## Offline Evidence

Golden fixture canonical UTF-8 length 1646; SHA-256:
a7bfd43b26e706c78ae43b0c8880ce80dae5d82b167e2fac666c3c49ea57ff37.
Working document check: exact digest/length, reordered-key canonical equality,
35/35 leaf mutations change digest. Mutation checks are hash diagnostics,
not schema validation or runnable model/provider qualification.
Independent staged export using Python standard json/hashlib reproduces
golden bytes/digest, frozen statuses and both exact document hashes.
Staged two-document tree: 45c39cb3a12ea4235ff532cba183ab8b497b6649.
Retained export: .ea4e92i-design-index-a.
git diff --cached --check passed. No pytest count carried forward as a new run.
Committed blob verification is required and recorded in Obsidian afterward.

## Remaining Authority Boundary

Pure implementation/tests are next; current registered binding is unchanged.
No transitive roll manifest is yet complete; no roll/reseal authorized here.
Historical records and unresolved provenance remain immutable/visible.
EA92E deployment HOLD persists. Source commit and runtime authority stay
separate from static binding identity. No actual policy enforcement proved.
No issuance, activation, listener, receiver/model/provider calls, config edits,
network/GPU/ComfyUI, downloads or deletion. Kilo/image pipeline untouched.
Exact resulting commit SHA needs separate normal push approval.
