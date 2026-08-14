# Release order and Patreon verification handoff

## Intent

Prevent a later chapter from running ahead of an unverified earlier chapter in the same novel and release stage. Require Patreon posts to survive a canonical URL reload with the expected persisted title, body, tier, schedule, and media before SQLite is marked verified.

## Functional commit

- Commit: `86cb784`
- Branch: `fix/release-order-patreon-verification`
- Files: `app.py`, `automation_db.py`, `release_automation_regression.py`, `tests/test_patreon_persisted_verification.py`

## Diff regions

- `automation_db.py`: `claim_next_release_job()` same-novel, same-stage earlier-chapter prerequisite.
- `app.py`: generated Patreon chapter-upload helper media readiness, canonical reload, persisted-field verification, and submit result gating.
- `release_automation_regression.py`: same-novel blocking and cross-novel independence tests.
- `tests/test_patreon_persisted_verification.py`: generated-helper persistence guard test.

## Change signature

The change must block later chapters only when an earlier chapter in the same novel and stage is not verified or cancelled. It must continue allowing an unrelated novel to run. Patreon verification must not accept generic page text such as `Scheduled for`; it must reload the saved post and compare persisted fields. The change must not alter release dates, tier assignments, chapter payload generation, or unrelated `app.py` features.

## Verification

- `python release_automation_regression.py`: 9 passed.
- Focused pytest set: 4 passed.
- `python -m py_compile automation_db.py app.py release_automation.py release_automation_regression.py`: passed.
- Generated Patreon Playwright helper: `node --check` passed.

Pre-existing unrelated working-tree changes were left unstaged and are not part of commit `86cb784`.

## Live repair follow-up (2026-08-14)

- Patreon HA 81-85 were repaired in place and reloaded from their canonical edit URLs.
- Each post now has the exact local title/body, one finished cover image, Inner Disciple-only access, 09:00 MST, and consecutive dates from 2026-08-17 through 2026-08-21.
- SQLite has one verified inner-disciple job per Patreon post ID and no duplicate release job keys.
- Commit `fb5d0d0` handles Patreon's segmented date input with native keystrokes and verifies the resulting value.
- Royal Road's public table ends at HA 65. HA 66 was incorrectly classified as `update_existing` only because Patreon existed and the local revision changed.
- Commit `e5957f9` restricts `update_existing` to chapters actually present on Royal Road. The rebuilt HA 66 pack is now `royal_road_ready`, `editExistingRoyalRoadChapter=false`, with the intended 2026-08-10 release date.
