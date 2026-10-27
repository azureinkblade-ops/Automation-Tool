# EA-4E.92TR GPU visibility inspect correction

Date: 2026-10-27

One user-approved independent read-only review of pinned 92TQ source
`892aaeb43dc55dbcfd7e40270654d3a01d9197ba` returned HOLD. The effective
Docker `Env` check converted values to a set, accepted `void`, and excluded
only the exact `all` value. A second non-void entry such as
`NVIDIA_VISIBLE_DEVICES=0` could therefore pass. The reviewer made no edits
and ran no tests or native calls.

The corrected source requires an actual list of strings and exactly one
`NVIDIA_VISIBLE_DEVICES=` entry, equal to `NVIDIA_VISIBLE_DEVICES=void`.
New fake tests deny `all`, device `0`, duplicate `void`, and missing `void`
before start. The focused strict non-live suite passed 99/99. No Docker,
model, GPU, receiver, or handoff call ran for this correction. Fake tests do
not qualify native behavior. A fresh independent review of corrected
committed source and a separate exact one-shot authorization are required.
Production remains HOLD.
