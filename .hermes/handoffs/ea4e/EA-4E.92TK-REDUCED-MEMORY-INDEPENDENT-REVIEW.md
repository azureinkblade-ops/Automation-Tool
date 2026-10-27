# EA-4E.92TK independent reduced-memory source review

Date: 2026-10-27

Pinned source: `473081b252f430aa37338364e45d6d5aa26ea711`.
One user-approved independent, read-only review returned PASS with no
hold-level finding. The reviewer confirmed that 8 GiB is permitted only for
the reduced-memory, mount-only non-model mode; the model-serving default
remains 20 GiB. The pinned image, read-only model mount, containment checks,
no-HTTP/no-inference return, exact ownership/cleanup, and fixed-category
startup handling remain in place. The reviewer inspected committed blobs
only, made no edits, and ran no tests or native calls.

The owner reran 80 focused strict non-live tests on the unchanged committed
tree. Local tracked source was clean and the remote branch matched the pinned
commit before this documentation change. Entrypoint SHA-256:
`0ec77dfeddde4fe6a2275d84330a715c3f9905334587520ec5a2a0727b3982e1`.
Runner SHA-256:
`e8fc98ad6520fd900473ddf866fe206b50be94df18d988031dc96c991d7f1bfc`.
Docker CLI SHA-256:
`c11b843b727ea76e6c63b393bccb73d957b6fcc12ba871c8265699e3a12e933c`.

Source review and fake tests do not establish native Docker behavior or the
cause of the earlier start failure. No native run occurred for 92TJ. A new
exact one-shot authorization is required. Production remains HOLD.
