# EA-4E.92WK Isolated Buildx layout-error review hold

Date: 2026-11-02 (America/Phoenix)
Status: INDEPENDENT READ-ONLY REVIEW HOLD / NO NATIVE RUN

One approved independent read-only review inspected committed 92WJ source at
`17af5cb7ffc454eb8bbf2f4d0231330da7e1d706` and returned HOLD for the
broad no-raw-`OSError` claim. The isolated `Popen` failure no longer retains
the raw launch error; ordinary Docker behavior and the pinned Windows root
were accepted as narrow corrections. But `_names` and `_sha256` in the layout
policy raise `LayoutDenied from None` inside `OSError` handlers, retaining raw
path-bearing errors in `__context__`. The tests cover only the `Popen` path.
The one-review authorization is consumed. No tests or executables ran during
this review.

The overall launcher remains HOLD for child-process/deadline containment,
plugin stability through launch, and independent builder-locality proof.
No Docker, Buildx, container, build, model, GPU, receiver, handoff, or
production action ran. Private model bytes and preserved Docker runtime
directories remain untouched. All native and production gates HOLD.
