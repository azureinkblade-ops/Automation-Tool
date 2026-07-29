# Safe Extraction of the Automation Tool Monolith — Implementation Plan (v2, GPT sign-off)

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
> Each task = one module slice, one PR-quality commit. NO big-bang rewrite. Respects CLAUDE.md + automation-tool-architecture risk #1 ("DO NOT attempt a big-bang refactor") + GPT Phase 1 sign-off (2026-07-16).

**Goal:** Break `app.py` (43,895 lines, 932 functions) into importable subsystem modules so future edits touch ~500-line files, not a 50K-line blob — without breaking the running app at any commit.

## Architecture (target end-state) — GPT-approved dependency direction
```
app.py
  ├── app_config.py
  ├── app_state.py
  ├── promo modules        (promo_copy.py, promo_builder.py)
  ├── release modules      (release_state.py, release_automation.py, approval_inbox.py)
  ├── publishing modules   (buffer_publish.py, browser_publish.py)
  └── analytics/video      (youtube_pipeline.py, growth_analytics.py)
```
**Rules (mandatory):**
- `app_config.py` = IMMUTABLE values: paths (`ROOT`, `*_OUTPUT_DIR`), constants, thresholds, `NOVEL_NAMES`, URLs, `LORA_STYLE_TRACKS`, `EXTERNAL_AI_ENABLED`. NEVER mutable state here.
- `app_state.py` = MUTABLE process-local runtime objects: caches, locks, thread refs, stop events. NEVER in `app_config.py`.
- Subsystem modules may import `config`, `state`, `automation_db`, and LOWER-LEVEL modules. **Subsystem modules must NEVER import `app`.**
- `app.py` imports EXPLICIT names only. **Never `from module import *`.**
- Tightly coupled functions stay in `app.py` until their dependencies are extracted (temporary compatibility wrappers OK; duplicate implementations NOT OK).
- One-way `release_automation → promo_builder` is acceptable IF `promo_builder` never imports `release_automation`.
- Create `app_config.py` + `app_state.py` FIRST (Task 0), not at inversion — don't pile the riskiest change into one commit.

## Phase 1 scope (GPT-approved: logic extraction only)
**Keep UNCHANGED:**
- The 149-branch HTTP dispatch (route names + payloads).
- Inline HTML/CSS/JavaScript.
- JSON + SQLite mirroring.
- Browser scripts + extension protocol.
- Port behavior (8765).
- No route table introduced; no frontend extraction. Document both for Phase 2 (Task: blueprint only).

## Existing feature identity — MOVE-AS-IS (GPT-approved)
Characterization tests written BEFORE moving each function. Relocation and behavioral redesign are SEPARATE commits. Preserve:
`build_patreon_draft`, `rotated_hashtags`, `rotated_x_hashtags`, `upload_all_for_chapter`, `auto_fix_weak_images`, `chapter_review_packs`.
Exception: imports may be restructured to remove `app.py` deps, but outputs/side-effects/filenames/status-flags/errors stay equivalent.

## Regression gate (GPT-corrected: NOT "same count")
- **Zero failures.**
- **All baseline test names still present.**
- **Final count >= baseline** (new characterization tests increase it).
- **Fresh-process import test for every module** (exposes circular imports).
- Additional required contracts:
  - `import app` AND every extracted module succeeds in a fresh subprocess.
  - Imports never start servers/workers/browsers/posting.
  - Representative API routes retain status codes + JSON keys.
  - Root HTML still contains critical control IDs.
  - JSON + SQLite mirrors BOTH update from extracted release-state calls.
  - Release jobs remain idempotent + tier-ordered.
  - Browser-result hard gates remain required before marking a release verified.
  - Image approval still blocks weak/unapproved media.
  - Buffer routing preserves Instagram post/reel type + TikTok/Short routing.
  - X stays within character limit.
  - No test performs live Buffer/Patreon/Royal Road/X/FB/YouTube writes.
  - File/folder naming unchanged (existing packs still open).
  - Background workers remain singletons.
  - Secrets never appear in logs or returned payloads.
  - `app.py` continues exposing compatibility names the current regression harness uses.

## Server-smoke rules (GPT: maintenance window only)
- **Do NOT run 8765 + 8766 concurrently** against this workspace (shared SQLite/JSON/Chrome-9222/workers).
- Live state (2026-07-16): server **8765 running**; release-automation thread stopped; story-hook stopped; but **SQLite still holds a RUNNING Royal Road job for EN-101** (orphan — release thread stopped but job not reconciled).
- Tasks 1–7: import tests + regression harness ONLY. Never restart live server.
- Task 8 (inversion): (a) finish/reconcile the EN-101 orphan job; (b) pick a maintenance window AFTER daily posting; (c) stop 8765; (d) start candidate on 8765; (e) GET-only `/`, `/api/health`, selected status routes; (f) confirm no worker unexpectedly starts; (g) stop candidate if validation fails, else leave verified instance running.

---

### Task 0: Baseline capture + create `app_config.py` + `app_state.py`
**Objective:** Lock the regression baseline; establish the two shared modules everything will import.
**Files:** Create `app_config.py`, `app_state.py`; Create `tests/test_imports_fresh.py`.
**Step 1:** Capture baseline: `python tools/regression_check.py 2>&1 | tee docs/REGRESSION_BASELINE.txt`. Record pass count + test names.
**Step 2:** Write `tests/test_imports_fresh.py` (spawns subprocess per module, asserts clean import, asserts no server/worker started):
```python
import subprocess, sys, os
REPO = r"C:\Users\David\Documents\Automation tool"
MODS = ["app_config","app_state","promo_copy","promo_builder","release_state",
        "release_automation","approval_inbox","buffer_publish","browser_publish",
        "youtube_pipeline","growth_analytics","app"]
def _import_clean(mod):
    code = f"import {mod}; print('OK')"
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=120)
    return r.returncode == 0 and "OK" in r.stdout and "Traceback" not in r.stderr
def test_all_modules_import_fresh():
    for m in MODS:
        assert _import_clean(m), f"{m} failed fresh import"
```
**Step 3:** Create `app_config.py` with IMMUTABLE values copied from `app.py`: `ROOT`, `NOVEL_NAMES`, `SOCIAL_OUTPUT_DIR`, `TIKTOK_OUTPUT_DIR`, `YOUTUBE_OUTPUT_DIR`, `EXPERIMENT_OUTPUT_DIR`, `LORA_STYLE_TRACKS`, `EXTERNAL_AI_ENABLED`, all URL/path constants, thresholds.
**Step 4:** Create `app_state.py` with MUTABLE objects: ledger cache dict + lock, `approval_cleared` cache + lock, any stop-events/thread refs. Initialize empty/singleton.
**Step 5:** In `app.py`, `import app_config as config`, `import app_state as state` at top (after stdlib). Replace direct constant refs with `config.X` and cache refs with `state.X` ONLY where trivial; do NOT delete app.py defs yet (Task 8). Verify `import app` still works + regression baseline unchanged.
**Step 6:** Commit `git add app_config.py app_state.py tests/test_imports_fresh.py app.py docs/REGRESSION_BASELINE.txt && git commit -m "refactor: add app_config + app_state; capture regression baseline"`

### Task 1: `promo_copy.py` — profiles, novel voices, hashtags, captions, CTAs
**Objective:** Extract pure copy-generation (no media I/O).
**Files:** Create `promo_copy.py`; Modify `app.py:3386` (`social_profile`), `:3440` (`rotated_hashtags`), `:3466` (`rotated_x_hashtags`), `:3486` (`compact_chapter_hook`), `:3082` (`focused_social_cta`), `:3141` (`engagement_prompt_line`), `:3178` (`platform_engagement_prompt_line`).
**Step 1:** Characterization test `tests/test_promo_copy.py`: `social_profile("EN")["name"]=="Eternal Nexus"`; `rotated_hashtags("EN","EN-mon",chapter_text="x") != rotated_hashtags("EN","EN-tue",chapter_text="x")` and `"#AzureInkblade" in a`; `focused_social_cta("EN","patreon")` returns str.
**Step 2:** FAIL (module missing).
**Step 3:** Implement — copy fns verbatim into `promo_copy.py`, importing only `config`, stdlib (`re`,`json`). Move any novel-voice/hook/CTA variant banks here too.
**Step 4:** PASS + import test + regression baseline retained.
**Step 5:** Wire: `from promo_copy import social_profile, rotated_hashtags, rotated_x_hashtags, ...` in `app.py`; keep app.py defs as thin compatibility wrappers calling the module (no duplicate impl).
**Step 6:** Commit.

### Task 2: `promo_builder.py` — campaign/social-image/TikTok/Shorts pack construction
**Objective:** Extract media-pack builders (imports `promo_copy`, `config`, `state`).
**Files:** Create `promo_builder.py`; Modify `app.py:3505` (`build_platform_posts`), `:17070` (`make_social_post`), `:15583` (`make_tiktok_pack`) + sibling pack builders.
**Step 1:** Test `tests/test_promo_builder.py`: `make_social_post("EN","monday","default",False,chapter_number="25")` returns dict w/ `instagram`/`x`/`facebook` keys containing `#AzureInkblade`; `make_tiktok_pack(...)` returns pack dict.
**Step 2:** FAIL.
**Step 3:** Implement — copy fns; import `promo_copy`, `config`, `state`, `automation_db`; for not-yet-extracted cross-deps (e.g. `chapter_keywords`, `fallback_social_copy`), leave those fns IN app.py and have `promo_builder` call them via an **injected collaborator** (default param `fallback_copy=fallback_social_copy`) OR keep the fn in app.py and wrap. Prefer: extract `chapter_keywords`/`fallback_social_copy` into `promo_copy.py` in Task 1 if pure, else inject.
**Step 4:** PASS + import + regression.
**Step 5:** Wire explicit imports; compatibility wrappers in app.py.
**Step 6:** Commit.

### Task 3: `release_state.py` — ledger, release status, queue state, dual-store writes
**Objective:** Extract state + JSON/SQLite mirror writes (the critical dual-store seam).
**Files:** Create `release_state.py`; Modify `app.py:19025` (`load_chapter_ledger`), `:19124` (`chapter_ledger_updates_for_folder`), `mirror_*_to_database` fns (~336-386), `release_status` helpers.
**Step 1:** Test `tests/test_release_state.py`: `load_chapter_ledger()` returns dict; `chapter_ledger_updates_for_folder(...)` updates cache + writes JSON+SQLite (monkeypatch fs + assert both).
**Step 2:** FAIL.
**Step 3:** Implement — copy fns; import `config`, `state`, `automation_db`. State lives in `state` (ledger cache + lock). Dual-store writes preserved EXACTLY.
**Step 4:** PASS + import + regression (assert JSON mirror + SQLite both updated — required contract).
**Step 5:** Wire explicit imports; compatibility wrappers.
**Step 6:** Commit.

### Task 4: `approval_inbox.py` — aggregation + clearing
**Objective:** Extract the #4 review surface aggregator.
**Files:** Create `approval_inbox.py`; Modify `app.py:7243` (`approval_inbox`), clearing fns.
**Step 1:** Test `tests/test_approval_inbox.py`: `approval_inbox()` returns `counts`+`total` (fixture ledger); image approval still blocks weak media (required contract — assert unapproved pack appears in result).
**Step 2:** FAIL.
**Step 3:** Implement — copy fns; import `release_state`, `config`, `state`, `automation_db`, lower modules. Do NOT import app.
**Step 4:** PASS + import + regression.
**Step 5:** Wire explicit imports; compatibility wrappers.
**Step 6:** Commit.

### Task 5: `release_automation.py` — orchestration + reconciliation
**Objective:** Extract release orchestration incl. the #4 move-as-is functions.
**Files:** Create `release_automation.py`; Modify `app.py:7297` (`chapter_review_packs`), `:7341` (`upload_all_for_chapter`), `:1101` (`auto_fix_weak_images`), `:27364` (`build_patreon_draft`) [move here per GPT: Patreon chapter publishing stays in release_automation], idempotency/tier-order logic.
**Step 1:** Characterization test `tests/test_release_automation.py` (reuses #4 verify): stub side-effects via injected collaborators (`patreon_builder`, `x_poster`, `fb_assist`, `buffer_poster`, `weak_fixer`, `channels_getter`); assert `upload_all_for_chapter` blocks when `needsReview`, chains when approved; `auto_fix_weak_images` calls `regenerate_weak_images(use_openai=False)`; release jobs idempotent + tier-ordered (required contracts).
**Step 2:** FAIL.
**Step 3:** Implement — copy fns MOVE-AS-IS (GPT #5); inject side-effect collaborators (Buffer request fn, browser launcher, clock, image generator) as default params; import `approval_inbox`, `promo_builder`, `release_state`, `config`, `state`, `automation_db`. **Never import app.**
**Step 4:** PASS (11/11 like #4) + import + regression.
**Step 5:** Wire explicit imports; compatibility wrappers.
**Step 6:** Commit.

### Task 6: `buffer_publish.py` + `browser_publish.py`
**Objective:** Extract Buffer API/routing and X/FB browser prep (separate modules per GPT).
**Files:** Create `buffer_publish.py` (`buffer_post_from_folder`, `configured_buffer_channels`, channel routing, Instagram post/reel + TikTok/Short routing preserved — required contract); Create `browser_publish.py` (`publish_x_post`, `manual_facebook_assist`, browser launcher injectable, X char-limit enforced — required contract).
**Step 1:** Test `tests/test_buffer_publish.py`: stub `buffer_graphql`; `buffer_post_from_folder(folder,["c1"],"tiktok","addToQueue")` returns `{"posts":[...]}`; assert Instagram post/reel type preserved in routing. Test `tests/test_browser_publish.py`: `publish_x_post` text <= X limit; browser launcher injectable (no real launch in test).
**Step 2:** FAIL.
**Step 3:** Implement — copy fns; inject `buffer_request`, `browser_launcher`, `clock` collaborators; import `config`,`state`,`automation_db`.
**Step 4:** PASS + import + regression.
**Step 5:** Wire explicit imports; compatibility wrappers.
**Step 6:** Commit.

### Task 7: `youtube_pipeline.py` (single module, split only if >1,500–2,000 lines) + `growth_analytics.py`
**Objective:** Extract YouTube subsystem + growth wrapper.
**Files:** Create `youtube_pipeline.py` (`youtube_build_status` + video/end-screen/pinned-comment helpers; YouTube queue lock/thread live HERE per GPT #3); Create `growth_analytics.py` (wraps `growth_scheduler` + metrics; metrics worker state HERE).
**Step 1:** Test `tests/test_youtube_pipeline.py`: `youtube_build_status(stub)` returns dict w/ `running` key. Test `tests/test_growth_analytics.py`: re-exports `growth_scheduler.VALID_NOVELS`.
**Step 2:** FAIL.
**Step 3:** Implement — copy fns; import `config`,`state`,`automation_db`, lower modules. If `youtube_pipeline.py` exceeds ~1,800 lines after copy, split into `youtube_build.py` + `youtube_assist.py` before Task 8.
**Step 4:** PASS + import + regression.
**Step 5:** Wire explicit imports; compatibility wrappers.
**Step 6:** Commit.

### Task 8: Inversion (MAINTENANCE WINDOW, after EN-101 reconcile)
**Objective:** Flip `app.py` to import modules as source of truth; delete duplicate defs; thin shell.
**Prereqs (GPT #7):** (a) reconcile/finish orphaned Royal Road job EN-101 in SQLite; (b) wait for maintenance window after daily posting; (c) STOP 8765.
**Files:** Modify `app.py` (remove extracted defs; top imports explicit names from all modules; keep ONLY HTTP Handler + response serialization + startup + inline UI + compatibility names the regression harness uses).
**Step 1:** Test `tests/test_app_shell.py`: fresh-subprocess `import app` succeeds; `app.social_profile("EN")["name"]=="Eternal Nexus"`; `app.upload_all_for_chapter` callable; HTML constant contains critical control IDs (e.g. `uploadAllBtn`, `autoFixWeakBtn`, `approvalInboxBtn`).
**Step 2:** FAIL (dupes / import order).
**Step 3:** Implement — delete each extracted def in `app.py`; ensure explicit `from promo_copy import ...` etc. at top. Resolve circular imports by moving any remaining shared constant into `config` / shared cache into `state`. Confirm NO module imports `app`.
**Step 4:** PASS all module import tests + regression (zero failures, baseline retained, count >= baseline).
**Step 5:** Smoke (GET-only, maintenance window): start candidate on 8765; `curl /` (200 + HTML w/ control IDs), `curl /api/health`, selected status routes; confirm no worker unexpectedly starts; stop candidate if fail, else leave running.
**Step 6:** Commit `git commit -m "refactor: app.py is a thin HTTP+UI shell over subsystem modules"`.

### Task 9: Phase 2 blueprint (docs only, NO changes)
**Objective:** Record 149-branch dispatch map + JSON-mirror list for future router + SQLite-as-truth.
**Files:** Create `docs/REFACTOR_MAP.md`.
**Step 1:** grep `self.path == "/api/..."` in `Handler` → route→function table.
**Step 2:** grep `mirror_*_to_database` + JSON shadow files → mirror table.
**Step 3:** Write `docs/REFACTOR_MAP.md` with both + "Phase 2 (future)" section (ROUTES dict; SQLite-as-truth; frontend extraction).
**Step 4:** Commit `git commit -m "docs: refactor map for Phase 2 router + store consolidation"`.

---

## Open operational items (NOT part of this plan)
- **Image generation is currently on fallback** (no torch/diffusers/transformers in app runtime; no CUDA toolkit). Local SD + Auto-Fix Weak are non-functional until resolved. User decision pending (CPU wheel / CUDA wheel+toolkit / separate GPU venv / leave it). Blocks nothing in Phase 1 (extraction is import/test-only); revisit after extraction or when user chooses.
- **Orphan Royal Road job EN-101** must be reconciled before Task 8 (noted in Task 8 prereqs).
