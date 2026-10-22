# EA-4E.92QO Inert Volume Denial Coverage

The 92QN independent review found no blocking source defect in the unwired
92QM volume ACL reader, but identified four missing inert denial cases and a
narrow wiring guard. This checkpoint changes tests only; the reader and its
production call graph are unchanged.

The injected reader now covers a closed non-null handle, an invalid non-null
handle, an ordinary exception after nonzero output assignments, and a failed
call with zero captured Win32 error. All return denial with zero public flags;
the preflight handle denials do not invoke the injected reader. The fixture
uses non-owning synthetic handles and never calls the Windows volume API.

The unwired-source guard scans tracked C# files outside tests for direct,
qualified `Ea4eDirectoryVolumeAclCandidate.Read` or `ReadWith` calls with
optional whitespace. It is a static regression guard, not proof against
reflection, aliasing, generated or untracked code, or future edits.

Focused tests passed 18/18; the adjacent inert matrix passed 134/134 before
staging. No native read, Docker mutation, Kilo/OpenCode receiver, model, GPU,
ComfyUI, or production action occurred. The 92QN source PASS remains scoped
to the reviewed 92QM blob. Native compatibility, issuer identity/effective
rights, real agent handoff, and production remain HOLD. Strict 92AT remains
REJECT.
