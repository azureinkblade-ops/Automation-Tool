# Consolidated Plan — Image-Fallback Hardening + Concurrency Governor + azink_main LoRA + YouTube Catch-up

> **For Hermes:** Execute task-by-task via `subagent-driven-development`. Load `automation-tool-architecture`,
> `automation-tool-app`, `automation-tool-operator-runbook`, `mlops/azure-inkblade-lora-prep`, `qa-testing-engineer`,
> and `plan` for every task. (Supersedes the earlier image-fallback-only plan file.)

**Goal:** (A) Stop the local-SDXL image pipeline from silently falling back to stock photos; (E) lock
a single LoRA style track per shorts/reels/TikTok video so frames never mix `azink_real` and
`azink_main` mid-clip; (B) cap concurrent python/heavy subprocesses so the tool stops exhausting
RAM; (C) train the `azink_main` LoRA reusing the proven `azink_real` recipe and keep `azink_comic`
(manhwa) on hold for sourcing; (D) after code is validated, produce the YouTube video missed today.

**Architecture:** All code changes are surgical inside the existing single-file `app.py` + small new
helper modules (no monolith refactor — `automation-tool-architecture` forbids big-bang). LoRA work
reuses existing `lora-training/` assets and the caption/segregation discipline from
`mlops/azure-inkblade-lora-prep`. Sequencing is memory-aware: cheap code fixes first (they lower RAM
pressure), heavy GPU training last and only as a background+notify job the user triggers.

**Tech Stack:** Python stdlib only for app edits; `tools/regression_check.py` harness; SDXL LoRA
training via the Codex-bundled torch python (`env -u PYTHONPATH -u PYTHONHOME`); FFmpeg for video.

---

## ASSUMPTIONS (correct me if wrong)
- "The LoRA training we did" = `azink_real` (realistic fantasy, already trained, 55 images).
- "Train the others" = `azink_main` (main-posts style, currently untrained). `azink_comic` (manhwa)
  is explicitly ON HOLD (legal: no scraping commercial titles; needs owned/commissioned/CC0).
- "Factor in the realistic image usage" = capture `azink_real`'s proven recipe (image count,
  resolution, caption convention, training profile, segregation rule) as a reusable baseline config
  that `azink_main` training reuses, so we don't re-derive it.
- "Make up the YouTube video" = run the app's YouTube pipeline for the chapter/day that was missed
  today (operator step, after code is green). Default = the app's next-due YouTube chapter; specify
  novel/chapter if different.
- Concurrency limiter targets BOTH (a) the app's internal heavy subprocess spawns (diffusers image
  gen + ffmpeg video render — the ~4–5 GB workers we saw) and (b) standalone tool scripts launched
  by the user/agent, so they don't pile up.
- **Style-lock (Workstream E):** a single shorts/reels/TikTok video must use ONE LoRA track
  end-to-end (e.g. all `azink_real` OR all `azink_main`), never a mix. This is a correctness/brand
  rule, not a preference — mixing tracks mid-video is a visible defect. Default track per pack =
  majority track of the available tagged assets; user can override via `forceStyle`/`loraTrack`.

---

## Workstream A — Image-provider no-silent-fallback (carried from prior plan)

### Task A1: Locate generator + provider-selection code
**Files:** `app.py` (grep-only — `search_files` fails on this 43K-line file).
**Step 1:** `grep -nE "def local_stable_diffusion_status|def create_local_stable_diffusion_image|def select_image_provider|def generate_image|ALLOW_EXTERNAL|fell_back|pexels|pixabay" app.py | head -40`
**Step 2:** Record line numbers. No edit.

### Task A2: Add `ALLOW_EXTERNAL_IMAGE_FALLBACK` flag (default refuse)
**Files:** Modify `app.py` (~line 46, after the env-scrub block from commit `1feb6db`).
**Step 1 (placeholder test):** Register `check_image_provider_no_silent_fallback` (full body in A5) returning a failing placeholder; run harness → FAIL.
**Step 2 (code):** after the env block add:
```python
# Layer-1 of diffusers protection: default False = never silently substitute Pexels/Pixabay for local SDXL.
ALLOW_EXTERNAL_IMAGE_FALLBACK = os.environ.get("ALLOW_EXTERNAL_IMAGE_FALLBACK", "").lower() in ("1","true","yes","on")
```
**Step 5 commit:** `git commit -m "feat(image): add ALLOW_EXTERNAL_IMAGE_FALLBACK policy flag (default refuse)"`

### Task A3: Make the generation wrapper fail-loud
**Files:** Modify `app.py` — the function from A1 that calls `create_local_stable_diffusion_image` and falls back.
**Step 1 (test):** extend A5 check to monkeypatch the generator to raise → assert `ok==False`, `fell_back==False`, no `pexels.com`/`pixabay.com` URL. Run → FAIL.
**Step 2 (code):**
```python
try:
    result = create_local_stable_diffusion_image(prompt, **kwargs)
    if result and getattr(result, "ok", True):
        return result
except Exception as exc:
    if not ALLOW_EXTERNAL_IMAGE_FALLBACK:
        print(f"[image-pipeline] WARNING local SDXL generation failed and external fallback is "
              f"DISABLED (refusing stock substitution): {exc}", flush=True)
        return {"ok": False, "error": f"local_sdxl_generation_failed:{exc}",
                "fell_back": False, "provider": "local_stable_diffusion"}
    print(f"[image-pipeline] WARNING local SDXL failed, FALLING BACK to external provider "
          f"(ALLOW_EXTERNAL_IMAGE_FALLBACK=1): {exc}", flush=True)
    # existing Pexels/Pixabay path, now loudly logged
```
**Step 5 commit:** `git commit -m "fix(image): refuse silent external fallback when local SDXL fails (fail-loud)"`

### Task A4: Verify live endpoint still selects local
Launch clean (background): `env -u PYTHONPATH -u PYTHONHOME <codex-python> tools/server_control.py --port 8765 --force --no-open`; wait for listener.
`curl /api/provider-strategy` → `readiness.local_stable_diffusion.ready==True`, `selectedImageProvider=="local_stable_diffusion"`.
Tail stdout → contains `[image-pipeline] diffusers local SDXL enabled`. No edit/commit.

### Task A5: Add regression check
**Files:** Modify `tools/regression_check.py` (add fn + register in CHECKS ~line 1238).
**Step 1 (full check):**
```python
def check_image_provider_no_silent_fallback() -> list[dict[str, object]]:
    results = []
    # (a) live polluted-env launch: poll /api/provider-strategy, assert ready+selected,
    #     assert stdout has "diffusers local SDXL enabled" and NO "FALLING BACK".
    # (b) importlib.import_module("app"); monkeypatch create_local_stable_diffusion_image to raise;
    #     call the wrapper from A1 with provider="local_stable_diffusion";
    #     assert out.get("ok") is False and out.get("fell_back") is False and no stock URL.
    # (fill in exact symbols from A1; reuse harness assert_result + launch/wait helpers)
    return results
```
Register in `CHECKS`. **Step 2:** run `tools/regression_check.py` → `image_provider_no_silent_fallback` PASS; no pre-existing check regresses.
**Step 5 commit:** `git commit -m "test(image): regression check for no-silent-external-fallback invariant"`

### Task A6: Document
**Files:** Modify `references/DIFFUSERS_PYTHONPATH_FIX.md` (add generation-time layer + flag); modify `automation-tool-app/SKILL.md` pitfall (layer 0 startup + layer 1 fail-loud + flag + check name).
**Step 5 commit:** `git commit -m "docs(image): document fail-loud fallback layer + ALLOW_EXTERNAL_IMAGE_FALLBACK"`

---

## Workstream E — Single-style lock per Shorts/Reels/TikTok video (avoids main/real flicker)

> **STATUS (2026-07-15): COMPLETE & verified.** `check_tiktok_pack_single_track` PASS. Implemented:
> sidecar tag (E1), `pack_track` lock defaulting to `main-posts` with `style` override (E2), deep-tiktok
> lock (E3), regression check (E4), SKILL.md pitfall updated to "FIXED" (E5). Frontend dropdowns added
> for Shorts/Reels + Deep TikTok. Committed as `feat(style): single-track lock (Workstream E)`.

### Root cause (verified this session)
- `LORA_STYLE_TRACKS` (`app.py:126`) defines three tracks: `main-posts`→`azink_main`,
  `comic-style`→`azink_comic`, `realistic-posts`→`azink_real`.
- TikTok/shorts/reels images are generated earlier by `create_local_stable_diffusion_image`
  (`app.py:31600`) with a per-prompt track chosen by `lora_track_for_prompt` (`app.py:7847`) or an
  explicit `lora_track`. Different prompts → different tracks.
- `list_tiktok_assets` (`app.py:15240`) groups images **only by `ABBR_CH_N` filename — no style/track
  tag**. `make_tiktok_pack` (`app.py:15392`) then blindly copies `group["files"][:3]` into the video.
- **No code enforces one track per pack** → a reel can open realistic (`azink_real`) and cut to a
  `main` (`azink_main`) frame. That is the exact mid-video style flicker reported.

### Task E1: Tag each generated image with its style track
**Files:** Modify `app.py` (`create_local_stable_diffusion_image` / the promo-image loop ~31597,
and `archive_generated_promo_image`).
**Step 1 (test):** add to `tools/regression_check.py` (`check_tiktok_pack_single_track` in E4) a
precondition test asserting generated tiktok assets carry a track sidecar; run → FAIL.
**Step 2 (code):** when writing a tiktok/asset image, also write a sibling `.<track>.track` marker
(or embed `track` into the asset JSON). Minimal: write `Path(target).with_suffix(target.suffix + ".track")`
containing the resolved track key. Do NOT change the filename grouping (breaks other consumers).
**Step 5 commit:** `git commit -m "feat(style): record LORA track sidecar for generated tiktok assets"`

### Task E2: Add a pack-level style-lock selector
**Files:** Modify `app.py` (`make_tiktok_pack` ~15392, `make_or_generate_tiktok_pack` ~15608,
and `prepare_tiktok_outro_image` ~15378).
**Step 1 (test):** extend E4 check — given a mock asset group with mixed-track images, the pack
must select ONE track and only include images of that track (or regenerate all in that track).
**Step 2 (code):** resolve `pack_track` once per pack:
- default = the **majority track** among the group's tagged images (deterministic, no mid-video flip);
- if a `forceStyle`/`loraTrack` is passed on the request, honor it (user override);
- filter `group["files"]` to `pack_track` images; if fewer than 3, regenerate the missing frames with
  `create_local_stable_diffusion_image(..., lora_track=pack_track)` (or pull from banked of that
  track) so the pack is fully one style. The outro image (`prepare_tiktok_outro_image`) must also use
  `pack_track`.
**Step 3:** run E4 check → PASS.
**Step 5 commit:** `git commit -m "fix(style): lock a single LORA track per shorts/reels/tiktok pack"`

### Task E3: Apply the same lock to Deep TikTok
**Files:** Modify `app.py` (deep-tiktok handler / `make_deep_tiktok_pack` — locate via
`grep -nE "def make_deep_tiktok|deep-tiktok"`).
**Step 1:** reuse the E2 `pack_track` resolution; ensure the deep pack's frames + any generated
images share one track. Add the same assertion to E4.
**Step 2:** run E4 → PASS.
**Step 5 commit:** `git commit -m "fix(style): apply single-track lock to deep TikTok packs"`

### Task E4: Regression check for single-track packs
**Files:** Modify `tools/regression_check.py` (add `check_tiktok_pack_single_track`, register in CHECKS).
**Step 1 (check body):** (a) mock `list_tiktok_assets` to return a group with mixed `main-posts` +
`realistic-posts` tagged images; call `make_tiktok_pack`; assert the returned `images` all share one
track (read sidecars) and `pack_track` is recorded in `metadata.json`; (b) assert a mixed-track group
with a `forceStyle` override yields only that override's track.
**Step 2:** run `tools/regression_check.py` → `check_tiktok_pack_single_track` PASS; no prior check regresses.
**Step 5 commit:** `git commit -m "test(style): regression check for single-track tiktok/shorts packs"`

### Task E5: Document the rule
**Files:** Modify `automation-tool-app/SKILL.md` (add pitfall: "shorts/reels must be one style track
end-to-end; never mix azink_real + azink_main in one video").
**Step 5 commit:** `git commit -m "docs(style): document single-track lock for shorts/reels/tiktok"`

---

## Workstream F — Style-track performance tracking (which LoRA style wins)

> **STATUS (2026-07-15): COMPLETE & verified.** `check_style_track_column` PASS (both assertions).
> Implemented: `style_track` column + guarded ALTER + SCHEMA_VERSION 5→6 (F1/F2), `record_post_style_track`
> + `backfill_style_tracks_from_packs` helpers, `tools/style_performance_report.py` (F3), regression check
> (F4). NOTE: `platform_post_metrics` had no writer before this session, so engagement rows only appear
> after Buffer metric collection runs; the report falls back to pack-coverage from `tiktok-posts` metadata.
> Committed as `feat(metrics): style_track column + report (Workstream F)`.

**Objective:** carry the `pack_track` (recorded in `metadata.json` by E2) into published-post metrics
so we can compare engagement by style (`azink_real` vs `azink_main` vs `azink_comic`). This is the
analytics half of the style-lock: E guarantees single-style packs; F makes single-style packs
measurable.

### Verified mechanics (this session)
- Metrics table: `platform_post_metrics` (`automation_db.py:539`) columns
  `metric_id, post_id, platform, window, source, collected_at, views, impressions, engagements,
  engagement_rate, result, notes, payload_json`. **No style column yet.**
- Migration pattern: `SCHEMA_VERSION = 5` (`automation_db.py:24`); `init_db` (line 191) runs
  `ALTER TABLE ... ADD COLUMN` guarded by a `PRAGMA table_info` membership check (see the
  `recovery_events.event_hash` example at 618–619). Never DROP; add columns + bump version.
- Publish path: `save_post_record` (app.py:9131) writes `metadata.json` (already holds `pack_track`
  from E2) and `mirror_post_record_to_database`. Metrics are written through a generic upsert
  (locate exact writer in Task F1).

### Task F1: Locate the metric-writer + record-mirror
**Files:** `automation_db.py`, `app.py` (read-only).
**Step 1:** `grep -nE "INSERT INTO platform_post_metrics|def .*metric|upsert.*metric|mirror_post_record_to_database|def .*record_metric" automation_db.py app.py`
**Step 2:** record the exact function(s) that insert/update a `platform_post_metrics` row and how
they receive `post_id` + the parent post record (which carries `metadata.json` / `pack_track`).
No edit.

### Task F2: Add `style_track` column (schema migration)
**Files:** Modify `automation_db.py` (`platform_post_metrics` DDL ~539 + `init_db` migration ~618).
**Step 1 (test):** extend `tools/regression_check.py` with `check_style_track_column` — assert
`PRAGMA table_info(platform_post_metrics)` includes `style_track` after `init_db` runs; run → FAIL.
**Step 2 (code):** add `style_track TEXT` to the `CREATE TABLE` (line 552 area) and in `init_db`
after the `recovery_events` block add:
```python
cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(platform_post_metrics)").fetchall()}
if "style_track" not in cols:
    conn.execute("ALTER TABLE platform_post_metrics ADD COLUMN style_track TEXT")
```
Bump `SCHEMA_VERSION = 6` (line 24) and add a `mirror_post_record_to_database` path that backfills
`style_track` from `metadata.json` if present (safe ALTER, no data loss).
**Step 3:** run F-check → PASS.
**Step 5 commit:** `git commit -m "feat(metrics): add style_track column to platform_post_metrics (SCHEMA_VERSION 6)"`

### Task F3: Thread `pack_track` into the metric row on publish
**Files:** Modify `app.py` (`save_post_record` ~9131 / the metric-writer from F1) + `automation_db.py`
metric upsert.
**Step 1 (test):** extend F-check — given a post record whose `metadata.json` has `pack_track`,
assert the resulting `platform_post_metrics` row has `style_track == pack_track`.
**Step 2 (code):** when writing a metric row, read `pack_track` from the post's `metadata.json`
(falls back to the record's `styleTrack` field) and set `style_track`. If neither exists, leave NULL
(legacy posts) — don't fabricate.
**Step 3:** run F-check → PASS.
**Step 5 commit:** `git commit -m "feat(metrics): record pack_track as style_track on publish"`

### Task F4: Aggregation report (style vs performance)
**Files:** Create `tools/style_performance_report.py` (read-only query tool).
**Step 1:** query `platform_post_metrics` grouped by `style_track` (joined to `platform_posts` for
platform), computing AVG(engagement_rate), SUM(views), COUNT(*) per style; emit a markdown/JSON
table. Default window = all; accept `--platform`, `--since`.
**Step 2:** smoke-run against the live DB (read-only) to confirm output shape; no mutation.
**Step 5 commit:** `git commit -m "feat(report): style-track vs engagement aggregation report"`

### Task F5: Document the analytics rule
**Files:** Modify `automation-tool-app/SKILL.md` (add: "style_track flows metadata→metrics;
use tools/style_performance_report.py to compare styles").
**Step 5 commit:** `git commit -m "docs(metrics): document style_track analytics + report tool"`

---

## Workstream B — Concurrency Governor (RAM pressure)

> **STATUS (2026-07-15): COMPLETE & verified.** `check_heavy_jobs_limited` PASS (cap=2, peak=2, shared
> singleton). Implemented: `tools/concurrency.py` (HeavyJobLimiter, MAX_CONCURRENT_HEAVY_JOBS default 2),
> `tools/test_concurrency.py` (PASS), wrapped diffusers spawn in `create_local_stable_diffusion_image`
> (app.py ~8000) + ffmpeg video render in `run_generated_video_builder` (app.py ~33567) behind the
> shared limiter, `tools/run_limited.py` standalone-script guard (MAX_PARALLEL_SCRIPTS default 3),
> regression check (B3). B5 RAM spike test is operator-optional (limiter unit-verified + wired).
> Committed as `feat(concurrency): HeavyJobLimiter + run_limited guard (Workstream B)`.

### Task B1: Discover heavy subprocess spawn sites
**Files:** `app.py` (read-only), `tools/` (read-only).
**Step 1:** `grep -nE "subprocess|Popen|os.system|create_local_stable_diffusion_image|ffmpeg|ThreadPoolExecutor|Thread\(|ThreadingHTTPServer" app.py | head -60`
**Step 2:** Identify the image-gen and video-render call sites + any executor/thread pools. Record line numbers + which are "heavy" (diffusers/ffmpeg).
**Step 3:** Also inventory standalone scripts that spawn: `tools/track_app_processes.py`, `tools/release_upload_tracker.py`, `tools/release_tracker.py`, watchers. Note how the user/agent launches them.

### Task B2: Add a central semaphore for heavy jobs
**Files:** Create `tools/concurrency.py` (small module, stdlib only).
**Step 1 (test):** write `tools/test_concurrency.py`:
```python
import time, threading
from tools.concurrency import HeavyJobLimiter
lim = HeavyJobLimiter(max_parallel=2)
starts = []
def job(i):
    with lim:
        starts.append(time.time()); time.sleep(0.2)
ts = [threading.Thread(target=job, args=(i,)) for i in range(5)]
[t.start() for t in ts]; [t.join() for t in ts]
# assert no more than 2 overlap: max concurrent == 2
```
Run → FAIL (module missing).
**Step 2 (code):** `tools/concurrency.py`:
```python
import threading, os
_DEFAULT = int(os.environ.get("MAX_CONCURRENT_HEAVY_JOBS", "2"))
class HeavyJobLimiter:
    def __init__(self, max_parallel=None):
        self._sem = threading.Semaphore(max_parallel or _DEFAULT)
    def __enter__(self): self._sem.acquire(); return self
    def __exit__(self, *a): self._sem.release()
```
**Step 3:** run `tools/test_concurrency.py` → PASS.
**Step 5 commit:** `git commit -m "feat(concurrency): add HeavyJobLimiter semaphore module + test"`

### Task B3: Wrap image-gen + video-render spawns with the limiter
**Files:** Modify `app.py` (the sites from B1).
**Step 1 (test):** extend `tools/regression_check.py` with `check_heavy_jobs_limited` — launch N concurrent image-gen calls (mock-free, against the live app with a tiny prompt), assert at most `MAX_CONCURRENT_HEAVY_JOBS` diffusers workers ever alive concurrently (poll `tasklist` for python processes or count in-flight via an instrumented counter). Run → FAIL.
**Step 2 (code):** at each heavy spawn site, wrap with `with HeavyJobLimiter():` (import at top). Leave non-heavy spawns (e.g. Playwright manual-assist) unwrapped unless they also spike RAM.
**Step 3:** run regression → PASS.
**Step 5 commit:** `git commit -m "fix(concurrency): gate diffusers + ffmpeg spawns behind HeavyJobLimiter"`

### Task B4: Standalone-script launch guard
**Files:** Create `tools/run_limited.py` (wrapper enforcing `MAX_PARALLEL_SCRIPTS`).
**Step 1:** `tools/run_limited.py` counts currently-running `python.exe` children launched by this tool (match on repo path + script name fragment, per the skill's "assemble pattern at runtime" pitfall) and queues/refuses beyond the cap instead of spawning another.
**Step 2:** Document in `automation-tool-app` SKILL.md runtime pitfalls: launch standalone trackers/watchers via `tools/run_limited.py` so they don't pile up.
**Step 5 commit:** `git commit -m "feat(concurrency): add run_limited.py guard for standalone tool scripts"`

### Task B5: Verify RAM behavior
**Files:** verify only.
**Step 1:** Launch app clean via hardened launcher. Fire 4 simultaneous Build-All-Posts-style image requests (or 4 `curl /api/campaign`). `tasklist | grep python.exe` → at most `MAX_CONCURRENT_HEAVY_JOBS` heavy workers; total python RAM bounded vs the prior ~8 GB double-worker spike.
**Step 2:** report before/after RAM. No commit.

---

## Workstream C — azink_main LoRA (reuse azink_real recipe; manhwa on hold)

### Task C1: Discover existing LoRA assets + training scripts
**Files:** read-only `lora-training/`, `loras/`, `tools/lora_training/`, `mlops/azure-inkblade-lora-prep` references.
**Step 1:** `ls -R lora-training loras tools/lora_training 2>/dev/null | head -80`; read `loras/realistic_posts/` + `lora-training/realistic-posts/train-1024/` (count 55, inspect one `.txt` caption).
**Step 2:** find any existing SDXL-LoRA trainer script (`grep -rln "lora_training|sdxl|train"` in tools/). Record exact paths — do NOT invent a trainer.
**Step 3:** read `references/clean-manhwa-sources.md` + `references/tiktok-migration-workflow.md` for the caption/segregation recipe.

### Task C2: Capture azink_real recipe as a reusable baseline config
**Files:** Create `lora-training/RECIPE.md` (or `lora-training/_baseline_recipe.json`).
**Step 1:** document from C1 evidence: image_count=55, resolution=1024², bs=1, bf16, grad_checkpoint, rank 16–32, optimizer=AdamW (no bitsandbytes), caption convention `<TRIGGER>, <scene>, chapter N <type>, <style>`, segregation rule (copy to subfolder, never root), VRAM cap <15 GB / temp <80 °C, GPU=RTX 4080 SUPER 16 GB.
**Step 2:** note `azink_real` TRIGGER + novel map (EN/Kael, HA/Kai, HP/Liang, SF/Jarek) from the skill.
**Step 5 commit:** `git commit -m "docs(lora): capture azink_real training recipe as reusable baseline"`

### Task C3: Prep azink_main training set (segregated + captioned)
**Files:** Modify `lora-training/main-posts/` (create if absent).
**Step 1:** follow `references/tiktok-migration-workflow.md` but for main-posts style: copy candidate images into `lora-training/main-posts/train-1024/` (or a `extra-*` subfolder per segregation rule), **exclude reel/animated/deep frames**, images only.
**Step 2:** caption each with TRIGGER `azink_main` using the C2 convention (reuse `tools/lora_training/caption_tiktok_ch20plus.py` pattern, adapted — copy to `scripts/`/`tools/lora_training/` as a new captioner if needed; do NOT mutate the real source).
**Step 3:** drop `novel-promo-card.png`-style text-overlay images (weak style signal per skill).
**Step 5 commit:** `git commit -m "data(lora): prepare segregated, captioned azink_main training set"`

### Task C4: Train azink_main (HEAVY — background + notify, backup first)
**Files:** uses trainer from C1 + C2 recipe + C3 set.
**Step 1 (backup, mandatory per memory note):** `cp automation_state.db automation_state.db.bak-lora-<ts>` and `cp -r lora-training lora-training.bak-lora-<ts>`.
**Step 2:** launch the existing trainer (from C1) with the C2 profile, via `terminal(background=true, notify_on_complete=true)` using `env -u PYTHONPATH -u PYTHONHOME <codex-python>`. Log VRAM/temp; abort if >15 GB / >80 °C.
**Step 3:** on completion, verify `loras/main_posts/pytorch_lora_weights.safetensors` exists and is non-trivial size; spot-check 2–3 generated samples for style fidelity (vision).
**Step 5 commit (after verification):** `git commit -m "train(lora): azink_main weights from captured recipe"`

### Task C5: Document manhwa (azink_comic) hold + sourcing path
**Files:** Modify `mlops/azure-inkblade-lora-prep/SKILL.md` (or a `references/manhwa-sourcing-blocker.md`).
**Step 1:** record the explicit hold: `azink_comic` training BLOCKED until license-clean manhwa
training images are sourced; permitted sources = owned art, commissioned (work-for-hire/ownership
agreement), CC0/CC-BY illustration sets; FORBIDDEN = scraping Webtoons/commercial titles (copyright +
datacenter-IP block). Reference `clean-manhwa-sources.md`.
**Step 2:** add a research TODO: find a viable license-clean manhwa-style source (e.g. CC-BY manhwa
anthologies, commissioned batches) before un-holding.
**Step 5 commit:** `git commit -m "docs(lora): record azink_comic hold + license-clean sourcing path"`

### Task C6: Regression + cleanup
Run `tools/regression_check.py` (A/B checks still green). Remove any temp caption/verify scripts. Report "temp files cleaned".

---

## Workstream D — YouTube catch-up (operator, after code green)

### Task D1: Produce the missed YouTube video
**Prereq:** Workstreams A + B merged & regression green; app running (hardened launcher).
**Step 1:** determine the missed chapter/day (default = app's next-due YouTube chapter via
`GET /api/youtube-build-status` or the daily-youtube endpoint; specify novel/chapter if different).
**Step 2:** `POST /api/youtube-text-video` (or `/api/youtube-text-build`) with the chapter text.
Verify outputs: `youtube-title.txt`, `youtube-description.txt`, `youtube-tags.txt`,
`youtube-voiceover.wav`, `youtube-video.mp4` in the expected folder; `make_youtube_video.py` builds
vertical MP4.
**Step 3:** review the rendered video via the UI Pack Health tab (user does visual QA, per the
"don't automate the user's QA" rule). Manual-assist upload/end-screens via `/api/youtube-helper/*`.
**Note:** this is an operator action, not a code change — no commit unless a pipeline bug is found
(in which case file it as a new task).

---

## Sequencing (memory-aware)
1. **A1–A6** (image fallback) — cheap, lowers risk of mislabeled stock; run regression with app up.
2. **B1–B5** (concurrency) — cheap code, directly reduces RAM; verify before/after.
3. **C1–C3** (LoRA prep) — disk/IO only, no GPU; safe anytime.
4. **C4** (LoRA train) — HEAVY GPU/RAM; background + notify; only when user is NOT also running app
   image-gen. Backup first.
5. **C5–C6** — docs + final regression.
6. **D1** (YouTube) — operator, after everything green.

## Risks / tradeoffs
- **A default-refuse:** a genuine diffusers outage now blocks image gen instead of degrading to
  stock. Intended (brand safety). Flip `ALLOW_EXTERNAL_IMAGE_FALLBACK=1` deliberately for fallback.
- **B limiter value:** default `MAX_CONCURRENT_HEAVY_JOBS=2` (each worker ~4–5 GB; 2 fits 16 GB VRAM
  with headroom). Tune down to 1 if RAM still spikes. The app is `ThreadingHTTPServer`, so concurrent
  HTTP requests CAN each spawn a worker — the semaphore is what actually bounds it.
- **C training cost:** ~16 GB VRAM, hours of GPU. Background + notify; never foreground (tooling
  quirk). Backup before.
- **C scope:** "train the others" interpreted as `azink_main` only; `azink_comic` held. If you meant
  additional targets, say so.
- **Scope guard:** no 43K-line refactor, no 149-branch dispatch change, no SQLite/JSON dual-store
  touch (per architecture skill).

## Skills to load during implementation
- `automation-tool-architecture` — safe surgical boundaries; "run regression after routing/state changes".
- `automation-tool-app` — `DIFFUSERS_PYTHONPATH_FIX.md`, BUILD_ALL_POSTS verify trap, "grep not search_files on app.py".
- `automation-tool-operator-runbook` — launch/health/YouTube pipeline; Chrome bridge for worker.
- `mlops/azure-inkblade-lora-prep` — LoRA inventory, caption convention, segregation, manhwa licensing.
- `qa-testing-engineer` — "silent failure is critical", Model Fallback Testing, Regression Protection Mandatory.
- `plan` — this structure (TDD bite-sized tasks).
- `requesting-code-review` — spec + code-quality gate before merge.
