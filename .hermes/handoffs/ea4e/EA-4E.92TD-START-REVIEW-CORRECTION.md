# EA-4E.92TD start-error review correction

Date: 2026-10-27

The one approved independent read-only review of pinned candidate
`86d2e927f730d8598e77a103cbf66e75c62282f2` returned HOLD. The
reviewer found that a failed-start reinspection could disprove ownership,
but cleanup still relied on an earlier ownership check and could attempt
to stop the container. The reviewer made no edits, ran no tests, and made
no Docker, Ollama, model, GPU, receiver, or handoff call. The one-review
authorization is consumed.

The source-only successor re-inspects exact ownership immediately before
any cleanup stop, even when earlier inspection had passed. A persistent
owner mismatch now causes uncertain-cleanup denial without stop, removal,
or log read. A fake regression covers that case; the prior transient
mismatch and stopped/running start-failure tests remain. Focused strict
non-live tests passed 69/69. No native run followed the review finding.

The corrected committed source needs a new independent read-only review.
Any native use still requires separate exact one-shot authorization that
accepts transient Docker-local logging. Fake tests do not qualify native
behavior or identify the 92TB start failure's cause. Production remains
HOLD.
