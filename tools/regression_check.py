from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import automation_db  # noqa: E402
import growth_scheduler  # noqa: E402


REPORT_PATH = ROOT / "regression-report.json"
HISTORY_PATH = ROOT / "regression-history.jsonl"
LOCAL_BASE_URL = "http://127.0.0.1:8765"


def result(name: str, ok: bool, detail: str = "", **extra: object) -> dict[str, object]:
    return {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
        **extra,
    }


def assert_result(name: str, condition: bool, detail: str = "", **extra: object) -> dict[str, object]:
    return result(name, bool(condition), detail if condition else f"FAILED: {detail}", **extra)


def timed_runner(name: str, runner: object) -> tuple[list[dict[str, object]], dict[str, object]]:
    started = time.time()
    try:
        checks = runner()  # type: ignore[operator]
    except Exception as exc:
        checks = [result(name, False, str(exc))]
    elapsed = time.time() - started
    return checks, {
        "runner": name,
        "elapsed": round(elapsed, 3),
        "checks": len(checks),
        "failed": len([item for item in checks if not item.get("ok")]),
    }


def fetch_local_json(path: str, timeout: float = 12.0) -> dict[str, object]:
    with urllib.request.urlopen(f"{LOCAL_BASE_URL}{path}", timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    return data if isinstance(data, dict) else {}


def server_health_snapshot() -> dict[str, object]:
    try:
        health = fetch_local_json("/api/health", timeout=8.0)
        return {
            "reachable": True,
            "pid": health.get("pid"),
            "processStartedAt": health.get("processStartedAt"),
            "sourceMtimeAtStart": health.get("sourceMtimeAtStart"),
            "appModifiedAt": health.get("appModifiedAt"),
            "isCurrent": str(health.get("sourceMtimeAtStart") or "") == str(health.get("appModifiedAt") or ""),
        }
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def recent_pack_folders(root: Path, limit: int = 8) -> list[Path]:
    if not root.exists():
        return []
    folders = [path for path in root.iterdir() if path.is_dir() and (path / "metadata.json").exists()]
    return sorted(folders, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def pack_has_reviewable_files(folder: Path) -> bool:
    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() in app.IMAGE_EXTENSIONS:
            name = path.name.lower()
            if name in {"youtube-thumbnail.png", "overlay-preview.jpg", "thumbnail.png"}:
                continue
            if name.startswith(("tiktok-clean-", "frame-", "thumb-")):
                continue
            return True
    return False


def check_youtube_queue() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    start = app.daily_youtube_start_chapter()
    items = app.youtube_daily_candidates()
    chapters = [
        int(item.get("chapter") or 0)
        for item in items
        if isinstance(item, dict) and str(item.get("chapter") or "").isdigit()
    ]
    checks.append(assert_result("youtube_queue_has_items", bool(chapters), f"items={[(i.get('abbr'), i.get('chapter')) for i in items]}"))
    checks.append(assert_result("youtube_queue_uses_start_floor", bool(chapters) and min(chapters) >= start, f"start={start}, chapters={chapters}"))
    if chapters:
        checks.append(assert_result("youtube_queue_targets_one_batch", len(set(chapters)) == 1, f"start={start}, chapters={chapters}"))
    checks.append(result("youtube_queue_snapshot", True, "", start=start, items=[{key: item.get(key) for key in ["abbr", "chapter", "title", "reason"]} for item in items]))
    return checks


def check_youtube_build_folder_resolution() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    folders = sorted(app.YOUTUBE_OUTPUT_DIR.glob("en-19-*"))
    if not folders:
        checks.append(result("youtube_chapter_folder_resolution_skipped", True, "No EN chapter 19 YouTube folder exists."))
        return checks
    folder = folders[-1].resolve()
    resolved = app.resolve_youtube_pack_folder_or_latest_story_hook(str(folder)).resolve()
    checks.append(
        assert_result(
            "youtube_chapter_folder_does_not_fallback_to_story_hook",
            resolved == folder,
            f"folder={folder}, resolved={resolved}",
        )
    )
    preflight = app.button_preflight(str(folder), "youtube_build")
    checks.append(
        assert_result(
            "youtube_build_preflight_keeps_chapter_folder",
            Path(str(preflight.get("folder") or "")).resolve() == folder,
            f"folder={folder}, preflight={preflight.get('folder')}",
            ok_flag=preflight.get("ok"),
            errors=preflight.get("errors"),
            warnings=preflight.get("warnings"),
        )
    )
    return checks


def check_pack_previews() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    roots = [app.OUTPUT_DIR, app.SOCIAL_OUTPUT_DIR, app.TIKTOK_OUTPUT_DIR]
    checked = 0
    failures: list[str] = []
    missing_preflight: list[str] = []
    for root in roots:
        for folder in recent_pack_folders(root):
            checked += 1
            try:
                preview = app.pack_preview(str(folder))
            except Exception as exc:
                failures.append(f"{folder}: {exc}")
                continue
            has_files = pack_has_reviewable_files(folder)
            image_cards = len(preview.get("imageCards") or [])
            if has_files and image_cards < 1:
                failures.append(f"{folder}: has image files but imageCards={image_cards}")
            preflight = preview.get("bufferPreflight")
            if not isinstance(preflight, dict) or "canPush" not in preflight or "nextAction" not in preflight:
                missing_preflight.append(str(folder))
    checks.append(assert_result("pack_preview_image_cards", not failures, f"checked={checked}", failures=failures[:12]))
    checks.append(assert_result("pack_preview_has_buffer_preflight", not missing_preflight, f"checked={checked}", missing=missing_preflight[:12]))
    return checks


def check_pack_preview_speed() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    folders: list[Path] = []
    for root in [app.OUTPUT_DIR, app.SOCIAL_OUTPUT_DIR, app.TIKTOK_OUTPUT_DIR]:
        folders.extend(recent_pack_folders(root, limit=3))
    if not folders:
        return [result("pack_preview_speed_skipped", True, "No recent pack folders were found.")]
    timings: list[dict[str, object]] = []
    slow: list[dict[str, object]] = []
    for folder in folders[:9]:
        started = time.time()
        preview = app.pack_preview(str(folder))
        elapsed = time.time() - started
        item = {
            "folder": folder.name,
            "elapsed": round(elapsed, 3),
            "cards": len(preview.get("imageCards") or []),
        }
        timings.append(item)
        if elapsed >= 1.5:
            slow.append(item)
    checks.append(
        assert_result(
            "pack_preview_fast_under_1_5s",
            not slow,
            f"checked={len(timings)}",
            timings=timings,
            slow=slow,
        )
    )
    return checks


def create_test_png(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (720, 1280), color=(30, 44, 60))
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 180, 640, 1100), outline=(91, 203, 255), width=8)
        draw.text((130, 580), "Regression image", fill=(255, 255, 255))
        image.save(path)
    except Exception:
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
            b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
        )


def check_tiktok_uses_supplied_chapter_text() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    original_docs = app.docs_chapter_text
    try:
        def fail_docs(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("docs lookup should not be needed when chapter text is supplied")

        app.docs_chapter_text = fail_docs  # type: ignore[assignment]
        overlays = app.tiktok_chapter_teaser_overlays(
            "EN",
            "998",
            "Eternal Nexus",
            chapter_text="Kai raised a silver sword as fire crossed the ruined bridge. The city watched from broken towers while the gate opened.",
            fallback_text="Fallback should not be needed.",
        )
        checks.append(assert_result("tiktok_supplied_text_returns_four_overlays", len(overlays) == 4, f"overlays={overlays}"))
        checks.append(assert_result("tiktok_overlay_from_supplied_text", any("SWORD" in str(item).upper() or "BRIDGE" in str(item).upper() or "CITY" in str(item).upper() for item in overlays), f"overlays={overlays}"))
    finally:
        app.docs_chapter_text = original_docs  # type: ignore[assignment]
    return checks


def check_build_all_posts_timing_panel() -> list[dict[str, object]]:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    required = [
        "function renderBuildTimingPanel",
        "function renderPackBufferPreflight",
        "recordTiming('Load selected chapter'",
        "recordTiming('Campaign pack'",
        "recordTiming('Shorts/Reels pack'",
        "recordTiming('Daily social post'",
        "recordTiming('Total before review'",
        "renderMasterReview({promo, tiktok, social, outputs, timings})",
    ]
    missing = [item for item in required if item not in source]
    return [
        assert_result(
            "build_all_posts_timing_panel_present",
            not missing,
            "Timing panel and stage probes are wired into Build All Posts.",
            missing=missing,
        )
    ]


def check_image_approval_roundtrip() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    folder = app.TIKTOK_OUTPUT_DIR / "_regression-image-approval"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / "regression-image.png"
    create_test_png(image)
    metadata = {
        "abbr": "EN",
        "novel": "Eternal Nexus",
        "chapter": "999",
        "title": "Regression Image Approval",
        "kind": "tiktok",
        "images": [str(image)],
        "caption": "Regression only. Do not post.",
        "packStatus": "needs_image_review",
    }
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    original_feedback = app.IMAGE_FEEDBACK_FILE.read_text(encoding="utf-8") if app.IMAGE_FEEDBACK_FILE.exists() else None
    try:
        preview = app.pack_preview(str(folder))
        checks.append(assert_result("approval_preview_has_card", len(preview.get("imageCards") or []) == 1, f"cards={len(preview.get('imageCards') or [])}"))

        rejected = app.set_pack_image_approval(str(folder), str(image), False)
        rejected_card = (rejected.get("imageCards") or [{}])[0]
        checks.append(assert_result("single_image_reject", bool(rejected_card.get("rejected")) and not bool(rejected_card.get("approved")), str(rejected_card)))

        approved = app.set_pack_image_approval(str(folder), str(image), True)
        approved_card = (approved.get("imageCards") or [{}])[0]
        checks.append(assert_result("single_image_approve", bool(approved_card.get("approved")) and not bool(approved_card.get("rejected")), str(approved_card)))

        pack = app.mark_image_review_approved(str(folder))
        saved = app.read_metadata(folder)
        checks.append(assert_result("pack_approve_marks_images", len(saved.get("approved_images") or []) >= 1, f"approved={saved.get('approved_images')}"))
        checks.append(assert_result("pack_approve_status", saved.get("packStatus") in {"needs_video_build", "ready_to_queue"}, f"status={saved.get('packStatus')}", response=pack))
    finally:
        if original_feedback is None:
            try:
                app.IMAGE_FEEDBACK_FILE.unlink()
            except OSError:
                pass
        else:
            app.IMAGE_FEEDBACK_FILE.write_text(original_feedback, encoding="utf-8")
        shutil.rmtree(folder, ignore_errors=True)
    return checks


def check_current_pack_test() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    folder = app.OUTPUT_DIR / "_regression-current-pack-test"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / "regression-promo.png"
    create_test_png(image)
    metadata = {
        "abbr": "EN",
        "novel": "Eternal Nexus",
        "chapter": "999",
        "title": "Regression Current Pack",
        "images": [str(image)],
        "approved_images": [str(image)],
        "caption": "Regression only. Do not post.",
        "patreon_note": "Regression only. Do not post.",
        "packStatus": "manual_review_ready",
    }
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    try:
        data = app.current_pack_test(str(folder))
        checks.append(assert_result("current_pack_test_passes_clean_pack", bool(data.get("ok")), data.get("summary", ""), blockers=data.get("blockers"), warnings=data.get("warnings")))
        checks.append(assert_result("current_pack_test_has_checks", len(data.get("checks") or []) >= 8, f"checks={len(data.get('checks') or [])}"))
        missing = app.current_pack_test("")
        checks.append(assert_result("current_pack_test_blocks_missing_pack", not bool(missing.get("ok")) and bool(missing.get("blockers")), str(missing.get("blockers"))))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return checks


def check_image_provider_trace() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    folder = app.OUTPUT_DIR / "_regression-provider-trace"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / "provider-trace.png"
    try:
        create_test_png(image)
        source = "local_fallback:regression"
        app.write_image_provider_trace(
            image,
            {
                "prompt": "Regression provider trace image, no external providers.",
                "selectedSource": source,
                "attempts": [
                    {"provider": "local_fallback", "ok": True, "elapsedSeconds": 0.001, "detail": "regression"}
                ],
            },
        )
        trace = app.read_image_provider_trace(image)
        metadata = {
            "abbr": "EN",
            "novel": "Eternal Nexus",
            "chapter": "999",
            "title": "Regression Provider Trace",
            "images": [str(image)],
            "caption": "Regression only. Do not post.",
            "image_sources": [source],
            "packStatus": "manual_review_ready",
        }
        (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        preview = app.pack_preview(str(folder))
        first_card = (preview.get("imageCards") or [{}])[0]
        checks.append(assert_result("image_provider_trace_written", bool(trace.get("selectedSource")), f"trace={trace}"))
        checks.append(assert_result("image_provider_trace_in_preview", bool(first_card.get("providerTrace", {}).get("selectedSource")), str(first_card.get("providerTrace"))))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return checks


def check_image_provider_no_silent_fallback() -> list[dict[str, object]]:
    """Layer-1 invariant: when local SDXL is the priority provider but generation fails and
    ALLOW_EXTERNAL_IMAGE_FALLBACK is unset (default), the wrapper must NOT silently substitute
    Pexels/Pixabay stock photos. It must flag the trace as refusedExternalFallback and fall
    through to the local emergency fallback image. Verified two ways:
      (a) the module flag exists and defaults to False (refuse);
      (b) monkeypatching create_local_stable_diffusion_image to raise yields a trace with
          refusedExternalFallback==True and a produced file whose source is NOT pexels/pixabay.
    """
    checks: list[dict[str, object]] = []
    # (a) flag default
    checks.append(assert_result(
        "image_provider_fallback_flag_default_refuse",
        getattr(app, "ALLOW_EXTERNAL_IMAGE_FALLBACK", True) is False,
        f"ALLOW_EXTERNAL_IMAGE_FALLBACK={getattr(app, 'ALLOW_EXTERNAL_IMAGE_FALLBACK', 'MISSING')}",
    ))
    folder = app.OUTPUT_DIR / "_regression-no-silent-fallback"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / "refuse-stock.png"
    create_test_png(image)
    real_fn = app.create_local_stable_diffusion_image
    try:
        def _raise(*_a, **_k):
            raise RuntimeError("injected SDXL generation failure for regression")
        app.create_local_stable_diffusion_image = _raise
        source = app.create_prompt_fallback_image(
            "Regression: refuse silent stock substitution", image, 1, abbr="EN",
            allow_banked=False, fresh=True,
        )
        trace = app.read_image_provider_trace(image)
        refused = bool(trace.get("refusedExternalFallback"))
        has_stock = "pexels" in str(source).lower() or "pixabay" in str(source).lower()
        produced = image.exists() and image.stat().st_size > 0
        checks.append(assert_result(
            "image_provider_refuses_silent_stock_fallback",
            refused and (not has_stock) and produced,
            f"source={source!r}, refused={refused}, produced={produced}, trace_keys={list(trace.keys())}",
        ))
    except Exception as exc:
        checks.append(assert_result("image_provider_refuses_silent_stock_fallback", False, f"harness error: {exc}"))
    finally:
        app.create_local_stable_diffusion_image = real_fn
        shutil.rmtree(folder, ignore_errors=True)
    return checks


def check_image_feedback_training_loop() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    folder = app.OUTPUT_DIR / "_regression-image-training-loop"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / "EN_training_feedback.png"
    create_test_png(image)
    metadata = {
        "abbr": "EN",
        "novel": "Eternal Nexus",
        "chapter": "999",
        "title": "Regression Training Feedback",
        "images": [str(image)],
        "caption": "Regression training approval image with sword bridge city.",
        "image_prompts": ["silver sword bridge city training feedback"],
        "packStatus": "manual_review_ready",
    }
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    original_feedback = app.IMAGE_FEEDBACK_FILE.read_text(encoding="utf-8") if app.IMAGE_FEEDBACK_FILE.exists() else None
    try:
        before = app.folder_quality_gate(str(folder), "instagram", full_duplicate_scan=False)
        app.record_image_feedback(image_path=image, action="approve", metadata={**metadata, "folder": str(folder), "qualityScore": 80}, note="Regression approved image at 80/100.")
        approved = app.folder_quality_gate(str(folder), "instagram", full_duplicate_scan=False)
        approved_score = float((approved.get("imageQuality", {}).get("items") or [{}])[0].get("score") or 0)
        before_score = float((before.get("imageQuality", {}).get("items") or [{}])[0].get("score") or 0)
        checks.append(assert_result("image_feedback_approval_raises_score", approved_score > before_score, f"before={before_score}, approved={approved_score}"))

        app.record_image_feedback(image_path=image, action="unapprove", metadata={**metadata, "folder": str(folder)}, note="Regression rejected image.")
        rejected = app.folder_quality_gate(str(folder), "instagram", full_duplicate_scan=False)
        rejected_score = float((rejected.get("imageQuality", {}).get("items") or [{}])[0].get("score") or 0)
        checks.append(assert_result("image_feedback_reject_blocks_image", rejected_score < approved_score and bool(rejected.get("errors")), f"approved={approved_score}, rejected={rejected_score}, errors={rejected.get('errors')}"))

        summary = app.image_feedback_training_summary("EN")
        checks.append(assert_result("image_training_summary_has_records", int(summary.get("records") or 0) >= 1, f"records={summary.get('records')}"))
        trainable_total = sum(int(bucket.get("trainable") or 0) for bucket in (summary.get("byNovel") or []))
        checks.append(assert_result("image_training_summary_tracks_trainable", trainable_total >= 1, f"trainable={trainable_total}"))
        strategy = app.provider_strategy_status()
        checks.append(assert_result("provider_strategy_exposes_training", isinstance(strategy.get("training"), dict), "training section present"))
    finally:
        if original_feedback is None:
            try:
                app.IMAGE_FEEDBACK_FILE.unlink()
            except OSError:
                pass
        else:
            app.IMAGE_FEEDBACK_FILE.write_text(original_feedback, encoding="utf-8")
        shutil.rmtree(folder, ignore_errors=True)
    return checks


def check_diffusers_primary_lora_layout() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    strategy = app.load_automation_strategy()
    priority = [str(item) for item in strategy.get("imageProviderPriority", [])]
    checks.append(
        assert_result(
            "diffusers_is_primary_image_provider",
            bool(priority) and priority[0] == "local_stable_diffusion",
            f"priority={priority}",
        )
    )
    status = app.local_stable_diffusion_status()
    lora = status.get("lora") if isinstance(status.get("lora"), dict) else {}
    tracks = lora.get("tracks") if isinstance(lora.get("tracks"), dict) else {}
    expected = {"main-posts", "comic-style", "realistic-posts"}
    missing = sorted(expected - set(tracks))
    missing_dirs: list[str] = []
    for track in expected:
        item = tracks.get(track) if isinstance(tracks, dict) else {}
        folders = item.get("folders") if isinstance(item, dict) else {}
        for name, folder in (folders or {}).items():
            if not Path(str(folder)).exists():
                missing_dirs.append(f"{track}/{name}")
    checks.append(
        assert_result(
            "lora_training_tracks_exist",
            not missing and not missing_dirs,
            f"tracks={sorted(tracks)}, missingDirs={missing_dirs[:8]}",
        )
    )
    comic_prompt = app.enhance_local_sd_prompt(
        "Kai faces a glowing system gate in the rain, manhwa panel",
        orientation="vertical",
        lora_track="comic-style",
    )
    realistic_prompt = app.enhance_local_sd_prompt(
        "A realistic cinematic alley scene with a wounded cultivator",
        orientation="vertical",
        lora_track="realistic-posts",
    )
    checks.append(
        assert_result(
            "lora_prompt_tokens_are_applied",
            "azink_comic" in comic_prompt and "azink_real" in realistic_prompt,
            f"comicHas={'azink_comic' in comic_prompt}, realHas={'azink_real' in realistic_prompt}",
        )
    )
    checks.append(
        assert_result(
            "local_sd_status_exposes_lora_tracks",
            isinstance(status.get("lora"), dict) and bool(tracks),
            f"ready={status.get('ready')}, loraEnabled={lora.get('enabled') if isinstance(lora, dict) else None}",
        )
    )
    return checks


def check_image_generation_batch_quality_report() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    folder = app.OUTPUT_DIR / "_regression-image-batch-quality"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        images = []
        for index in range(4):
            image = folder / f"realistic_batch_{index + 1}.png"
            create_test_png(image)
            sidecar = image.with_suffix(image.suffix + ".local-sd.json")
            sidecar.write_text(
                json.dumps(
                    {
                        "provider": "local_stable_diffusion",
                        "model": "models/sdxl-base",
                        "loraLoaded": index < 3,
                        "prompt": "azink_real cinematic realistic fantasy portrait with rune knight and dragon temple",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            images.append(image)
        app.record_image_feedback(
            image_path=images[0],
            action="approve",
            metadata={"abbr": "EN", "qualityScore": 90, "folder": str(folder), "title": "Regression realistic batch"},
            note="Regression training-grade image at 90/100.",
        )
        app.record_image_feedback(
            image_path=images[1],
            action="approve",
            metadata={"abbr": "EN", "qualityScore": 82, "folder": str(folder), "title": "Regression realistic batch"},
            note="Regression training-grade image at 82/100.",
        )
        report = app.image_generation_batch_quality_report(folder, abbr="EN", persist=True)
        checks.append(assert_result("image_batch_report_created", (folder / "image-generation-quality-report.json").exists(), "report file exists"))
        checks.append(assert_result("image_batch_report_counts_images", int(report.get("total") or 0) == 4, f"total={report.get('total')}"))
        checks.append(assert_result("image_batch_report_tracks_pass_rate", float(report.get("passRate") or 0) >= 0.85, f"passRate={report.get('passRate')}, items={report.get('items')}"))
        checks.append(assert_result("image_batch_report_tracks_training_rate", int(report.get("trainingGrade") or 0) >= 2, f"trainingGrade={report.get('trainingGrade')}"))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return checks


def check_pack_health_speed() -> list[dict[str, object]]:
    timings = []
    data = {}
    for _ in range(2):
        started = time.time()
        data = app.pack_health_panel(10, fast=True)
        timings.append(time.time() - started)
        if timings[-1] < 3.0:
            break
    elapsed = min(timings) if timings else 0.0
    return [
        assert_result(
            "pack_health_fast_under_3s",
            elapsed < 3.0,
            f"elapsed={elapsed:.2f}s, count={data.get('count')}, attempts={[round(item, 3) for item in timings]}",
            elapsed=round(elapsed, 3),
            count=data.get("count"),
            attempts=[round(item, 3) for item in timings],
        ),
    ]


def check_approval_inbox_speed() -> list[dict[str, object]]:
    started = time.time()
    data = app.approval_inbox()
    elapsed = time.time() - started
    return [
        assert_result(
            "approval_inbox_fast_under_5s",
            elapsed < 5.0,
            f"elapsed={elapsed:.2f}s, total={data.get('total')}, counts={data.get('counts')}",
            elapsed=round(elapsed, 3),
            total=data.get("total"),
            counts=data.get("counts"),
        ),
    ]


def check_live_server_routes() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    health = server_health_snapshot()
    checks.append(assert_result("live_server_reachable", bool(health.get("reachable")), str(health), health=health))
    if not health.get("reachable"):
        return checks
    checks.append(assert_result("live_server_uses_current_source", bool(health.get("isCurrent")), str(health), health=health))

    started = time.time()
    try:
        provider = fetch_local_json("/api/provider-strategy", timeout=20.0)
        elapsed = time.time() - started
        training = provider.get("training") if isinstance(provider.get("training"), dict) else {}
        guidance = provider.get("learnedPromptGuidance") if isinstance(provider.get("learnedPromptGuidance"), dict) else {}
        checks.append(
            assert_result(
                "live_provider_strategy_has_training",
                int(training.get("records") or 0) >= 1 and all(key in guidance for key in app.NOVEL_NAMES),
                f"elapsed={elapsed:.2f}s, records={training.get('records')}, guidance={list(guidance.keys())}",
                elapsed=round(elapsed, 3),
                records=training.get("records"),
                guidanceKeys=list(guidance.keys()),
            )
        )
    except Exception as exc:
        checks.append(result("live_provider_strategy_has_training", False, str(exc)))

    started = time.time()
    try:
        health_panel = fetch_local_json("/api/pack-health?limit=10&fast=1", timeout=20.0)
        elapsed = time.time() - started
        checks.append(
            assert_result(
                "live_pack_health_fast",
                elapsed < 5.0 and int(health_panel.get("count") or 0) > 0,
                f"elapsed={elapsed:.2f}s, count={health_panel.get('count')}, needs={health_panel.get('needsAttention')}",
                elapsed=round(elapsed, 3),
                count=health_panel.get("count"),
                needsAttention=health_panel.get("needsAttention"),
            )
        )
    except Exception as exc:
        checks.append(result("live_pack_health_fast", False, str(exc)))

    preview_folder = ""
    for root in [app.TIKTOK_OUTPUT_DIR, app.SOCIAL_OUTPUT_DIR, app.OUTPUT_DIR]:
        recent = recent_pack_folders(root, 1)
        if recent:
            preview_folder = str(recent[0])
            break
    if not preview_folder:
        checks.append(result("live_pack_preview_skipped", True, "No recent pack folder found."))
        return checks
    started = time.time()
    try:
        preview_path = "/api/pack-preview?folder=" + urllib.parse.quote(preview_folder)
        preview = fetch_local_json(preview_path, timeout=20.0)
        elapsed = time.time() - started
        preflight = preview.get("bufferPreflight") if isinstance(preview.get("bufferPreflight"), dict) else {}
        checks.append(
            assert_result(
                "live_pack_preview_has_image_cards_and_preflight",
                bool(preview.get("ok")) and len(preview.get("imageCards") or []) >= 1 and "canPush" in preflight,
                f"elapsed={elapsed:.2f}s, folder={Path(preview_folder).name}, cards={len(preview.get('imageCards') or [])}, preflightKeys={list(preflight.keys())}",
                elapsed=round(elapsed, 3),
                folder=preview_folder,
                cards=len(preview.get("imageCards") or []),
                preflightKeys=list(preflight.keys()),
            )
        )
    except Exception as exc:
        checks.append(result("live_pack_preview_has_image_cards_and_preflight", False, str(exc), folder=preview_folder))
    return checks


def check_weekend_post_prereqs() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    images = app.list_daily_promo_images()
    by_day: dict[str, set[str]] = {"Saturday": set(), "Sunday": set()}
    for item in images:
        day = str(item.get("day") or "")
        abbr = str(item.get("abbr") or "")
        path = Path(str(item.get("path") or ""))
        if day in by_day and abbr and path.exists():
            by_day[day].add(abbr)
    expected = set(app.NOVEL_NAMES)
    missing = {day: sorted(expected - abbrs) for day, abbrs in by_day.items()}
    checks.append(
        assert_result(
            "weekend_images_exist_for_all_novels",
            all(not values for values in missing.values()),
            f"available={{{', '.join(f'{day}: {sorted(values)}' for day, values in by_day.items())}}}",
            missing=missing,
        )
    )

    copy_failures: list[str] = []
    for day in ["Saturday", "Sunday"]:
        for abbr in sorted(expected):
            try:
                copy = app.weekend_social_copy(abbr, day)
            except Exception as exc:
                copy_failures.append(f"{abbr} {day}: {exc}")
                continue
            instagram = str(copy.get("instagram") or "")
            facebook = str(copy.get("facebook") or "")
            x_text = str(copy.get("x") or "")
            if app.linktree_url() not in instagram:
                copy_failures.append(f"{abbr} {day}: instagram missing Linktree hub")
            old_link_count = sum(1 for link in [app.PATREON_URL, app.TIKTOK_URL, app.YOUTUBE_SOCIAL_URL] if link in instagram)
            if old_link_count >= 2:
                copy_failures.append(f"{abbr} {day}: instagram still lists too many separate social links")
            if not facebook.strip():
                copy_failures.append(f"{abbr} {day}: facebook copy blank")
            if not x_text.strip() or len(x_text) > 280:
                copy_failures.append(f"{abbr} {day}: x copy invalid length={len(x_text)}")
            if "Chapter " in instagram or " Ch. " in instagram:
                copy_failures.append(f"{abbr} {day}: weekend copy appears chapter-specific")
    checks.append(
        assert_result(
            "weekend_copy_ready_without_building_posts",
            not copy_failures,
            "Weekend copy can be previewed without creating or pushing posts.",
            failures=copy_failures[:16],
        )
    )
    return checks


def check_linktree_dynamic_caption_engine() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    context = f"regression_dynamic_{int(time.time())}"
    ctas = [
        app.focused_social_cta("HA", "weekly_general_promo", context, "instagram")
        for _ in range(4)
    ]
    checks.append(
        assert_result(
            "dynamic_cta_rotates_copy",
            len(set(ctas)) >= 2 and all(app.linktree_url() in item for item in ctas),
            f"ctas={ctas}",
        )
    )
    copy = app.build_platform_posts(
        "Chapter 999: Regression",
        "Kai saw the gate open under the rain. The system blinked once and offered a choice no one else could see.",
        {
            "abbr": "HA",
            "novel": "Heavenly Ascension System",
            "chapter": "999",
            "phrases": ["The system blinked once and offered a choice no one else could see."],
            "release_status": {"royalRoadExists": True},
        },
    )
    caption = str(copy.get("caption") or "")
    facebook = str(copy.get("facebook_post") or "")
    x_post = str(copy.get("x_post") or "")
    checks.append(
        assert_result(
            "platform_posts_use_linktree_hub",
            app.linktree_url() in caption and app.linktree_url() in facebook and app.linktree_url() in x_post,
            f"captionHas={app.linktree_url() in caption}, facebookHas={app.linktree_url() in facebook}, xHas={app.linktree_url() in x_post}",
        )
    )
    old_link_count = sum(1 for link in [app.PATREON_URL, app.TIKTOK_URL, app.YOUTUBE_SOCIAL_URL] if link in caption)
    checks.append(
        assert_result(
            "platform_posts_do_not_list_all_social_links",
            old_link_count < 2,
            f"oldLinkCount={old_link_count}",
        )
    )
    checks.append(
        assert_result(
            "platform_posts_are_platform_adapted",
            caption.strip() != facebook.strip() and len(x_post) <= 280 and "I am using these posts" in facebook,
            f"instagramLen={len(caption)}, facebookLen={len(facebook)}, xLen={len(x_post)}",
        )
    )
    tiktok = app.tiktok_caption("HA", "999")
    reel = app.instagram_reel_caption("HA", "999")
    checks.append(
        assert_result(
            "shorts_and_reels_use_distinct_caption_voice",
            tiktok != reel and app.linktree_url() in tiktok and app.linktree_url() in reel,
            f"tiktokLen={len(tiktok)}, reelLen={len(reel)}",
        )
    )
    return checks


def check_deep_tiktok_weekend_workflow() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    try:
        app.write_animated_reel_builder_script(
            app.TIKTOK_OUTPUT_DIR,
            [],
            app.TIKTOK_OUTPUT_DIR,
            [],
            target_duration=68,
            deep=True,
        )
        directory_audio_rejected = False
    except RuntimeError:
        directory_audio_rejected = True
    checks.append(
        assert_result(
            "deep_tiktok_rejects_directory_as_audio",
            directory_audio_rejected,
            "The video builder must accept an audio file, never a folder path.",
        )
    )
    packs = app.existing_deep_tiktok_packs(include_completed=False, limit=8, fast=True)
    checks.append(assert_result("deep_tiktok_active_packs_visible", bool(packs), f"count={len(packs)}"))
    ready = [pack for pack in packs if pack.get("ready")]
    checks.append(assert_result("deep_tiktok_has_ready_pack", bool(ready), f"ready={len(ready)}, count={len(packs)}"))
    duration_failures: list[str] = []
    for pack in ready:
        duration = float(pack.get("duration") or 0)
        if duration < 60 or duration > 90:
            duration_failures.append(f"{pack.get('folder')}: duration={duration}")
    checks.append(
        assert_result(
            "deep_tiktok_ready_packs_are_long_form",
            not duration_failures,
            f"ready={len(ready)}",
            failures=duration_failures[:8],
        )
    )
    if packs:
        folder = str(packs[0].get("folder") or "")
        try:
            preview = app.deep_tiktok_pack_from_folder(folder)
            candidate_images = preview.get("candidate_images") or []
            included_images = preview.get("included_images") or []
            checks.append(
                assert_result(
                    "deep_tiktok_pack_preview_has_images",
                    len(candidate_images) >= len(included_images) >= 1,
                    f"folder={Path(folder).name}, candidates={len(candidate_images)}, included={len(included_images)}",
                )
            )
        except Exception as exc:
            checks.append(result("deep_tiktok_pack_preview_has_images", False, str(exc), folder=folder))
    try:
        live = fetch_local_json("/api/deep-tiktok-packs?includeCompleted=0&limit=8&fast=1", timeout=20.0)
        live_packs = live.get("packs") if isinstance(live.get("packs"), list) else live.get("items")
        checks.append(
            assert_result(
                "live_deep_tiktok_packs_route",
                isinstance(live_packs, list),
                f"keys={list(live.keys())}",
                count=len(live_packs) if isinstance(live_packs, list) else None,
            )
        )
    except Exception as exc:
        checks.append(result("live_deep_tiktok_packs_route", False, str(exc)))
    return checks


def check_story_hook_pack_readiness() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    data = app.story_hook_video_packs(limit=8, fast=True)
    items = data.get("items") if isinstance(data.get("items"), list) else []
    checks.append(assert_result("story_hook_packs_visible", bool(items), f"count={len(items)}"))
    buildable = [item for item in items if item.get("canBuild") or item.get("videoExists")]
    checks.append(assert_result("story_hook_packs_have_rebuild_source_or_video", bool(buildable), f"buildable={len(buildable)}, count={len(items)}"))
    ready = [item for item in items if item.get("videoExists") and item.get("thumbnail") and item.get("captions")]
    checks.append(assert_result("story_hook_ready_pack_has_video_thumbnail_captions", bool(ready), f"ready={len(ready)}, count={len(items)}"))
    folder_errors: list[str] = []
    for item in items[:5]:
        folder = Path(str(item.get("folder") or ""))
        if not folder.exists():
            folder_errors.append(f"{item.get('title')}: folder missing")
            continue
        if not app.story_hook_folder_has_rebuild_source(folder) and not item.get("videoExists"):
            folder_errors.append(f"{folder.name}: no builder, story text, or finished video")
    checks.append(
        assert_result(
            "story_hook_recent_folders_recoverable",
            not folder_errors,
            f"checked={min(5, len(items))}",
            failures=folder_errors,
        )
    )
    legacy_hosts = ("patreon.com", "royalroad.com", "youtube.com", "tiktok.com", "x.com")
    description_errors: list[str] = []
    for item in items:
        folder = Path(str(item.get("folder") or ""))
        description_file = folder / "youtube-description.txt"
        description = description_file.read_text(encoding="utf-8", errors="replace") if description_file.exists() else ""
        legacy = [host for host in legacy_hosts if host in description.lower()]
        if description.count(app.linktree_url()) != 1 or legacy:
            description_errors.append(f"{folder.name}: linktree={description.count(app.linktree_url())}, legacy={legacy}")
    checks.append(
        assert_result(
            "story_hook_descriptions_use_single_linktree_cta",
            not description_errors,
            f"checked={len(items)}",
            failures=description_errors,
        )
    )
    try:
        live = fetch_local_json("/api/story-hook-video-packs?limit=8&fast=1", timeout=20.0)
        live_items = live.get("items")
        checks.append(
            assert_result(
                "live_story_hook_packs_route",
                isinstance(live_items, list),
                f"keys={list(live.keys())}",
                count=len(live_items) if isinstance(live_items, list) else None,
            )
        )
    except Exception as exc:
        checks.append(result("live_story_hook_packs_route", False, str(exc)))
    return checks


def check_chapter_path_separation() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    labels = app.release_workflow_path_labels()
    required = {"dailyPromo", "releaseUpload", "fullYouTube", "variants"}
    checks.append(
        assert_result(
            "chapter_paths_have_separate_labels",
            required.issubset(set(labels)),
            f"labels={labels}",
            missing=sorted(required - set(labels)),
        )
    )
    upload = app.release_upload_path_status()
    posting = app.active_chapter_path_status()
    upload_rows = upload.get("novels") if isinstance(upload.get("novels"), list) else []
    posting_rows = posting.get("novels") if isinstance(posting.get("novels"), list) else []
    checks.append(assert_result("release_upload_path_declares_independence", "independent" in str(upload.get("note") or "").lower(), str(upload.get("note") or "")))
    checks.append(assert_result("release_upload_has_per_novel_rows", len(upload_rows) == len(app.NOVEL_NAMES), f"rows={len(upload_rows)}"))
    checks.append(assert_result("daily_promo_has_per_novel_rows", len(posting_rows) == len(app.NOVEL_NAMES), f"rows={len(posting_rows)}"))
    leaked = [
        item.get("abbr")
        for item in upload_rows
        if "postingNextChapter" not in item or "nextChapter" not in item
    ]
    checks.append(assert_result("release_upload_keeps_posting_reference_separate", not leaked, f"leaked={leaked}", leaked=leaked))
    return checks


def check_docs_refresh_fallback_message() -> list[dict[str, object]]:
    original = app.docs_chapter_index
    try:
        def blocked_docs(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise OSError("[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions")

        app.docs_chapter_index = blocked_docs  # type: ignore[assignment]
        items = app.youtube_daily_candidates()
    finally:
        app.docs_chapter_index = original  # type: ignore[assignment]
    reasons = [str(item.get("reason") or "") for item in items if isinstance(item, dict)]
    return [
        assert_result("docs_refresh_fallback_returns_candidates", bool(items), f"items={[(item.get('abbr'), item.get('chapter')) for item in items]}"),
        assert_result(
            "docs_refresh_fallback_message_is_clear",
            bool(reasons) and all("GitHub Docs refresh unavailable" in reason and "local ledger fallback" in reason for reason in reasons),
            f"reasons={reasons[:4]}",
        ),
    ]


def check_buffer_dry_run_routes() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    tiktok_folder = next(
        (
            folder for folder in recent_pack_folders(app.TIKTOK_OUTPUT_DIR, 12)
            if not folder.name.lower().endswith("-deep")
        ),
        None,
    )
    social_folder = next(
        (
            folder for folder in recent_pack_folders(app.SOCIAL_OUTPUT_DIR, 24)
            if app.media_files_for_folder(folder)
            and not folder.name.lower().startswith(("royal-road-", "release-"))
        ),
        None,
    )
    if tiktok_folder:
        dry = app.buffer_dry_run_from_folder(str(tiktok_folder), "tiktok", "draft")
        send_services = sorted(route.get("service") for route in dry.get("routes", []) if route.get("wouldSend"))
        checks.append(
            assert_result(
                "buffer_dry_run_short_routes_to_all_short_channels",
                {"instagram", "tiktok", "youtube"}.issubset(set(send_services)),
                f"folder={tiktok_folder.name}, services={send_services}, errors={dry.get('errors')}",
                dryRunOk=dry.get("ok"),
                warnings=dry.get("warnings"),
            )
        )
    else:
        checks.append(result("buffer_dry_run_short_routes_to_all_short_channels", True, "No recent non-deep TikTok folder found."))
    if social_folder:
        dry = app.buffer_dry_run_from_folder(str(social_folder), "instagram", "draft")
        send_services = sorted(route.get("service") for route in dry.get("routes", []) if route.get("wouldSend"))
        checks.append(
            assert_result(
                "buffer_dry_run_social_routes_to_instagram_only",
                send_services == ["instagram"],
                f"folder={social_folder.name}, services={send_services}, errors={dry.get('errors')}",
                dryRunOk=dry.get("ok"),
                warnings=dry.get("warnings"),
            )
        )
    else:
        checks.append(result("buffer_dry_run_social_routes_to_instagram_only", True, "No recent social folder found."))
    return checks


def check_pack_health_social_preview_controls() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    panel = app.pack_health_panel(10, fast=True)
    social_folder = next(
        (
            Path(str(item.get("folder") or ""))
            for item in panel.get("items", [])
            if "social-posts" in str(item.get("folder") or "").lower()
        ),
        None,
    )
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    checks.append(
        assert_result(
            "pack_health_has_social_preview_buttons",
            'data-pack-platform-action="x"' in source
            and 'data-pack-platform-action="facebook"' in source,
            "Pack Health should expose direct Preview X and Preview Facebook buttons.",
        )
    )
    checks.append(
        assert_result(
            "pack_health_social_buttons_use_preview_helper",
            "socialPostPreviewForFolder(currentFolder, ['x'])" in source
            and "socialPostPreviewForFolder(currentFolder, ['facebook'])" in source,
            "Pack Health social buttons should use the working social preview helper.",
        )
    )
    checks.append(
        assert_result(
            "social_preview_verifies_x_and_facebook_composers",
            '(("x", "X"), ("facebook", "Facebook"))' in source
            and "The {platform_label} composer did not confirm that the caption was populated." in source,
            "X and Facebook previews should fail clearly unless the browser confirms that the composer was filled.",
        )
    )
    original_gate = app.ensure_quality_gate
    original_playwright = app.playwright_available
    original_open = app.open_url_once
    try:
        app.ensure_quality_gate = lambda *_args, **_kwargs: None
        app.playwright_available = lambda: False
        app.open_url_once = lambda *_args, **_kwargs: None
        if social_folder and social_folder.exists():
            preview = app.social_post_preview(str(social_folder), use_playwright=False, platforms=["x", "facebook"])
            platforms = sorted(item.get("key") for item in preview.get("platforms", []) if item.get("key"))
            missing_media = [item.get("key") for item in preview.get("platforms", []) if not item.get("media_path")]
            checks.append(
                assert_result(
                    "weekend_social_preview_has_x_facebook_media",
                    platforms == ["facebook", "x"] and not missing_media,
                    f"folder={social_folder.name}, platforms={platforms}, missingMedia={missing_media}",
                )
            )
        else:
            checks.append(result("weekend_social_preview_has_x_facebook_media", True, "No social post folder found in recent Pack Health results."))

        campaign_folder = next(iter(recent_pack_folders(app.OUTPUT_DIR, 8)), None)
        if campaign_folder:
            preview = app.social_post_preview(str(campaign_folder), use_playwright=False, platforms=["x", "facebook"])
            platforms = sorted(item.get("key") for item in preview.get("platforms", []) if item.get("key"))
            missing_text = [item.get("key") for item in preview.get("platforms", []) if not str(item.get("text") or "").strip()]
            missing_media = [item.get("key") for item in preview.get("platforms", []) if not Path(str(item.get("media_path") or "")).is_file()]
            wrong_chapter_media = [
                item.get("key")
                for item in preview.get("platforms", [])
                if Path(str(item.get("media_path") or "")).is_file()
                and Path(str(item.get("source_folder") or "")) == campaign_folder
                and Path(str(item.get("media_path") or "")).parent != campaign_folder
            ]
            checks.append(
                assert_result(
                    "campaign_open_pack_preview_prefills_x_and_facebook",
                    platforms == ["facebook", "x"] and not missing_text and not missing_media and not wrong_chapter_media,
                    f"folder={campaign_folder.name}, platforms={platforms}, missingText={missing_text}, missingMedia={missing_media}, wrongChapterMedia={wrong_chapter_media}",
                )
            )
        else:
            checks.append(result("campaign_open_pack_preview_prefills_x_and_facebook", True, "No recent campaign folder found."))
    finally:
        app.ensure_quality_gate = original_gate
        app.playwright_available = original_playwright
        app.open_url_once = original_open
    return checks


def check_full_youtube_ready_artifacts() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    folders = [
        folder for folder in sorted(app.YOUTUBE_OUTPUT_DIR.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)
        if folder.is_dir() and (folder / "metadata.json").exists() and (folder / "youtube-video.mp4").exists()
    ][:8]
    if not folders:
        return [result("full_youtube_ready_artifacts_skipped", True, "No rendered full YouTube folders found.")]
    failures: list[str] = []
    for folder in folders:
        video = folder / "youtube-video.mp4"
        dims = app.media_dimensions(video)
        width = int(dims.get("width") or 0)
        height = int(dims.get("height") or 0)
        ratio_ok = bool(width and height and abs((width / max(1, height)) - (16 / 9)) <= 0.05)
        if not app.media_file_valid(video, "v:0"):
            failures.append(f"{folder.name}: video stream missing")
        if not app.media_file_valid(video, "a:0"):
            failures.append(f"{folder.name}: audio stream missing")
        if not ratio_ok:
            failures.append(f"{folder.name}: not 16:9 ({width}x{height})")
        if not (folder / "youtube-captions.srt").exists():
            failures.append(f"{folder.name}: captions missing")
        if not (folder / "youtube-thumbnail.png").exists():
            failures.append(f"{folder.name}: thumbnail missing")
    checks.append(
        assert_result(
            "full_youtube_ready_artifacts_valid",
            not failures,
            f"checked={len(folders)}",
            failures=failures[:12],
        )
    )
    return checks


def check_approval_inbox_cleared_filter() -> list[dict[str, object]]:
    fake = {
        "abbr": "EN",
        "chapter": "999",
        "platform": "x",
        "folder": str(app.SOCIAL_OUTPUT_DIR / "_regression-cleared-item"),
        "commentId": "regression-cleared-item",
    }
    key = app.approval_item_key("manualSocial", fake)
    state = {"schemaVersion": 1, "items": {key: {"kind": "manualSocial", "reason": "regression"}}}
    filtered = app.filter_uncleared_approval_items("manualSocial", [fake], cleared_state=state, active_paths={"EN": 999})
    active_mismatch = app.filter_uncleared_approval_items("manualSocial", [fake], cleared_state={"items": {}}, active_paths={"EN": 1})
    return [
        assert_result("approval_cleared_item_stays_hidden", not filtered, f"filtered={filtered}"),
        assert_result("approval_inbox_respects_active_path_filter", not active_mismatch, f"filtered={active_mismatch}"),
    ]


def check_weekly_growth_planner() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    week = "2026-07-13"
    slots = growth_scheduler.weighted_novel_slots({"HA": 2, "EN": 1, "HP": 1, "SF": 1}, week)
    checks.append(assert_result("weekly_growth_has_five_novel_slots", len(slots) == 5, f"slots={slots}"))
    checks.append(assert_result("weekly_growth_respects_weights", slots.count("HA") == 2 and all(slots.count(abbr) == 1 for abbr in ("EN", "HP", "SF")), f"slots={slots}"))
    checks.append(assert_result("weekly_growth_avoids_adjacent_novel_repeat", all(slots[index] != slots[index - 1] for index in range(1, len(slots))), f"slots={slots}"))

    context = {abbr: {"chapter": 22, "title": f"Regression {abbr}"} for abbr in growth_scheduler.NOVEL_ORDER}
    plan = growth_scheduler.build_weekly_growth_plan(
        week_start=week,
        weights={"HA": 2, "EN": 1, "HP": 1, "SF": 1},
        novels=app.NOVEL_NAMES,
        chapter_context=context,
        history=[],
    )
    rows = plan.get("slots") or []
    checks.append(assert_result("weekly_growth_is_seven_day_plan", len(rows) == 7, f"rows={len(rows)}"))
    checks.append(assert_result("weekly_growth_weekdays_are_one_novel_each", all(row.get("type") == "novel" and row.get("abbr") for row in rows[:5]), str([(row.get("day"), row.get("abbr")) for row in rows[:5]])))
    checks.append(assert_result("weekly_growth_has_community_and_recap", rows[5].get("type") == "community_poll" and rows[6].get("type") == "recap", str([row.get("type") for row in rows])))
    checks.append(assert_result("weekly_growth_uses_one_goal_per_slot", all(row.get("engagementGoal") in growth_scheduler.GOALS for row in rows), str([row.get("engagementGoal") for row in rows])))
    checks.append(assert_result("weekly_growth_is_linktree_first", all(growth_scheduler.LINKTREE_URL in " ".join((row.get("platformCopy") or {}).values()) for row in rows), "Every slot should include the Linktree hub."))
    checks.append(assert_result(
        "weekly_growth_copy_is_platform_native",
        all(
            len(str((row.get("platformCopy") or {}).get("x") or "")) <= 280
            and set((row.get("platformCopy") or {})) == {"instagram", "tiktok", "x", "facebook", "youtube"}
            and len(set((row.get("platformCopy") or {}).values())) == 5
            for row in rows
        ),
        "X copy must fit 280 characters and all five platforms must receive distinct copy.",
    ))
    checks.append(assert_result(
        "weekly_growth_ctas_are_specific_actions",
        all(
            "chapter is live" not in variant.lower()
            and any(token in variant.lower() for token in ("share", "tag", "comment", "verdict", "predict", "send", "follow", "subscribe", "start", "read", "find", "choose", "pass"))
            for variants in growth_scheduler.GOAL_CTAS.values()
            for variant in variants
        ),
        "Every CTA must request a concrete action and avoid generic release announcements.",
    ))
    checks.append(assert_result(
        "weekly_growth_tiktok_hooks_open_with_tension",
        all(
            any(token in str((row.get("platformCopy") or {}).get("tiktok") or "").splitlines()[0].lower() for token in ("price", "choice", "survived", "power", "surrender", "consequence", "?"))
            for row in rows[:5]
        ),
        "Every weekday TikTok preview should open with conflict, mystery, or a consequential decision.",
    ))
    checks.append(assert_result(
        "weekly_growth_instagram_is_emotional",
        all("feel the consequence" in str((row.get("platformCopy") or {}).get("instagram") or "").lower() for row in rows),
        "Instagram previews should use immersive, emotional language.",
    ))
    checks.append(assert_result(
        "weekly_growth_facebook_invites_discussion",
        all("?" in str((row.get("platformCopy") or {}).get("facebook") or "") and "tell me below" in str((row.get("platformCopy") or {}).get("facebook") or "").lower() for row in rows),
        "Facebook previews should explicitly invite discussion.",
    ))
    checks.append(assert_result(
        "weekly_growth_youtube_is_seo_rich",
        all(
            all(token in str((row.get("platformCopy") or {}).get("youtube") or "").lower() for token in ("progression fantasy", "web novel", "azure inkblade"))
            and growth_scheduler.LINKTREE_URL in str((row.get("platformCopy") or {}).get("youtube") or "")
            for row in rows
        ),
        "YouTube previews should include discoverable genre terms, the brand, and the Linktree destination.",
    ))
    checks.append(assert_result("weekly_growth_scores_every_slot", all(isinstance((row.get("predictedEngagement") or {}).get("score"), int) for row in rows), str([row.get("predictedEngagement", {}).get("score") for row in rows])))
    checks.append(assert_result("weekly_growth_default_plan_clears_quality_gate", bool(plan.get("summary", {}).get("ready")) and int(plan.get("summary", {}).get("diversityWarnings") or 0) == 0, str(plan.get("summary"))))

    weak = growth_scheduler.engagement_score(hook="Live", cta="Go", goal="", platform_copy={}, history=[])
    checks.append(assert_result("weekly_growth_flags_score_under_70", bool(weak.get("weak")) and float(weak.get("score") or 100) < 70, str(weak)))
    duplicate = growth_scheduler.engagement_score(
        hook="A repeated hook with enough words to normally score well for this regression test.",
        cta="Follow for the next chapter.", goal="Followers",
        platform_copy={name: f"Adapted {name} {growth_scheduler.LINKTREE_URL}" for name in ("instagram", "tiktok", "x", "facebook")},
        image_ref="same.png",
        history=[{"hook": "A repeated hook with enough words to normally score well for this regression test.", "cta": "Follow for the next chapter.", "imageRef": "same.png"}],
    )
    diversity = duplicate.get("diversity") or {}
    checks.append(assert_result("weekly_growth_detects_duplicate_hook_cta_image", all(diversity.get(key) for key in ("repeatedHook", "repeatedCta", "repeatedImage")), str(diversity)))

    with tempfile.TemporaryDirectory(prefix="weekly-growth-regression-", ignore_cleanup_errors=True) as temp:
        root = Path(temp)
        saved = automation_db.save_weekly_growth_plan(root, plan)
        saved_again = automation_db.save_weekly_growth_plan(root, plan)
        loaded = automation_db.get_weekly_growth_plan(root, week)
        status = automation_db.database_status(root)
        checks.append(assert_result("weekly_growth_database_roundtrip", bool(loaded) and loaded.get("planId") == plan.get("planId"), f"loaded={loaded.get('planId') if loaded else None}"))
        checks.append(assert_result("weekly_growth_database_upsert_is_idempotent", saved.get("planId") == saved_again.get("planId") and status.get("counts", {}).get("weekly_growth_plans") == 1 and status.get("counts", {}).get("weekly_growth_slots") == 7, str(status.get("counts"))))

    source = (ROOT / "app.py").read_text(encoding="utf-8")
    checks.append(assert_result("weekly_growth_ui_and_api_are_wired", 'id="weeklyGrowthBuildBtn"' in source and '"/api/weekly-growth-planner"' in source and "renderWeeklyGrowthPlan" in source, "Weekly planner UI/API wiring should exist."))
    return checks


def run_once() -> dict[str, object]:
    app.load_env_file()
    all_checks: list[dict[str, object]] = []
    runner_timings: list[dict[str, object]] = []
    for runner in [
        check_youtube_queue,
        check_youtube_build_folder_resolution,
        check_pack_previews,
        check_pack_preview_speed,
        check_tiktok_uses_supplied_chapter_text,
        check_build_all_posts_timing_panel,
        check_image_approval_roundtrip,
        check_current_pack_test,
        check_image_provider_trace,
        check_image_provider_no_silent_fallback,
        check_image_feedback_training_loop,
        check_diffusers_primary_lora_layout,
        check_image_generation_batch_quality_report,
        check_pack_health_speed,
        check_approval_inbox_speed,
        check_live_server_routes,
        check_weekend_post_prereqs,
        check_linktree_dynamic_caption_engine,
        check_deep_tiktok_weekend_workflow,
        check_story_hook_pack_readiness,
        check_chapter_path_separation,
        check_docs_refresh_fallback_message,
        check_buffer_dry_run_routes,
        check_pack_health_social_preview_controls,
        check_full_youtube_ready_artifacts,
        check_approval_inbox_cleared_filter,
        check_weekly_growth_planner,
    ]:
        checks, timing = timed_runner(runner.__name__, runner)
        all_checks.extend(checks)
        runner_timings.append(timing)

    failed = [item for item in all_checks if not item.get("ok")]
    report = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ok": not failed,
        "failed": len(failed),
        "server": server_health_snapshot(),
        "runnerTimings": runner_timings,
        "checks": all_checks,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "generatedAt": report["generatedAt"],
            "ok": report["ok"],
            "failed": report["failed"],
            "server": report["server"],
            "runnerTimings": runner_timings,
            "failedChecks": [item.get("name") for item in failed],
        }) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Automation Tool regression checks.")
    parser.add_argument("--repeat", type=int, default=1, help="Run the full regression suite this many times.")
    parser.add_argument("--stop-on-fail", action="store_true", help="Stop repeated runs after the first failure.")
    args = parser.parse_args()

    reports = []
    repeat = max(1, int(args.repeat or 1))
    for index in range(repeat):
        report = run_once()
        report["run"] = index + 1
        reports.append(report)
        if args.stop_on_fail and not report.get("ok"):
            break
    summary = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "runs": len(reports),
        "ok": all(bool(report.get("ok")) for report in reports),
        "failedRuns": len([report for report in reports if not report.get("ok")]),
        "reports": reports,
    }
    print(json.dumps(summary if repeat > 1 else reports[-1], indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
