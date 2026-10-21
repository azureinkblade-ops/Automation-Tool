# EA-4E.92PX First-Child Plan Binding

92PW's self-review found that its native owner would accept an arbitrary
nonempty path and any structurally valid directory descriptor. 92PX makes the
pre-call screen require the exact first child of the canonical four-component
ProgramData install plan and the exact planned SDDL. It also checks that the
caller-provided manifest root matches the expected namespace. The fixture
exercises wrong child, manifest, descriptor, and share mask denials without
invoking the native export.

The resolved known-folder path, pinned manifest root, and app SID remain
caller-supplied; this screen does not authenticate them or establish a trusted
installer. There is still no production caller, native runtime result,
effective-rights proof, durable one-use ledger, or live model handoff.
The strict 92AT invariant remains REJECT and production remains HOLD.

Verification before staging: focused inert checks 7/7, adjacent unique
non-live matrix 80/80. An initial adjacent run failed fixture compilation
after a required readback constant was accidentally removed; it was restored
before the passing rerun. No native directory or receiver/model action ran.
