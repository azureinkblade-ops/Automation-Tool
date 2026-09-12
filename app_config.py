"""Immutable configuration for the Automation Tool.

Holds values that never change at runtime: paths (ROOT-based), URLs,
thresholds, novel/style metadata, and external-AI enablement. This module has
NO mutable state and NO side effects at import time beyond reading env vars into
frozen-ish constants. Mutable runtime objects (locks, threads, caches) live in
app_state.py so a future Codex-runtime refresh cannot wipe process-local state,
and so subsystem modules can import config without pulling in the app shell.

Source of truth before extraction: app.py top-level constants (lines ~92-310).
Extracted per the consolidation plan; behavior is unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

# ROOT is the project directory (the folder containing app.py).
ROOT = Path(__file__).resolve().parent

# --- Output / asset directories (all ROOT-relative) ---
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
LOCAL_FFMPEG_DIR = ROOT / "tools" / "ffmpeg"
SOCIAL_OUTPUT_DIR = ROOT / "social-posts"
SOCIAL_PROMPT_FILE = ROOT / "social_prompt_template.txt"
TIKTOK_OUTPUT_DIR = ROOT / "tiktok-posts"
CHAPTER_OUTPUT_DIR = ROOT / "chapters"
CHAPTER_RETRY_DIR = ROOT / "chapter-retry-context"
YOUTUBE_OUTPUT_DIR = ROOT / "youtube-videos"
STORY_HOOK_OUTPUT_DIR = ROOT / "story-hook-videos"
MANUAL_VIDEO_OUTPUT_DIR = ROOT / "manual-video-packs"
OUTPUT_DIR = ROOT / "campaigns"
MANUAL_VIDEO_IMAGE_BANK_DIR = ROOT / "manual-video-image-bank"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
EXPERIMENT_OUTPUT_DIR = ROOT / "experiment-post-packs"
LOCAL_IMAGE_GENERATOR_SCRIPT = ROOT / "local_image_generator.py"
LORA_TRAINING_DIR = ROOT / "lora-training"
LORA_MODEL_DIR = ROOT / "loras"
GITHUB_MEDIA_DIR = ROOT / "docs" / "media"
PROMO_ROTATION_STATE_FILE = ROOT / "promo-image-rotation.json"
BACKGROUND_VIDEO_USAGE_FILE = ROOT / "background-video-usage.json"
BACKGROUND_VIDEO_BANK_TARGET = int(os.environ.get("BACKGROUND_VIDEO_BANK_TARGET", "20"))
YOUTUBE_BACKGROUND_CLIPS_MIN = int(os.environ.get("YOUTUBE_BACKGROUND_CLIPS_MIN", "2"))
YOUTUBE_BACKGROUND_CLIPS_MAX = int(os.environ.get("YOUTUBE_BACKGROUND_CLIPS_MAX", "3"))
GITHUB_REMOTE_URL = os.environ.get("GITHUB_REMOTE_URL", "https://github.com/azureinkblade-ops/Automation-tool.git")
GITHUB_MEDIA_REMOTE_URL = os.environ.get("GITHUB_MEDIA_REMOTE_URL", "https://github.com/azureinkblade-ops/Automation-Media.git")
GITHUB_MEDIA_REPO_DIR = Path(os.environ.get("GITHUB_MEDIA_REPO_DIR", str(ROOT / ".automation-media-repo")))
DEFAULT_GITHUB_PUBLIC_MEDIA_BASE_URL = "https://raw.githubusercontent.com/azureinkblade-ops/Automation-Media/main/media"
META_GRAPH_API_VERSION = os.environ.get("META_GRAPH_API_VERSION", "v25.0")
PATREON_URL = "https://www.patreon.com/c/azureinkblade"
YOUTUBE_SOCIAL_URL = "https://www.youtube.com/channel/UCBKiJENwFqvVIItR4WbMY6A"
TIKTOK_URL = "https://www.tiktok.com/@azureinkblade"
INSTAGRAM_URL = "https://www.instagram.com/azureinkblade"
LINKTREE_URL = os.environ.get("LINKTREE_URL", "https://linktr.ee/azureinkblade").strip() or "https://linktr.ee/azureinkblade"

# --- State / JSON-shadow file paths (SQLite is canonical; JSON kept for read-compat) ---
CHAPTER_RELEASE_QUEUE_FILE = ROOT / "chapter-release-queue.json"
RELEASE_STATUS_FILE = ROOT / "release_status.json"
CHAPTER_LEDGER_FILE = ROOT / "chapter_ledger.json"
CHAPTER_PATH_FILE = ROOT / "chapter-path-state.json"
YOUTUBE_DAILY_STATUS_FILE = ROOT / "youtube_daily_queue_status.json"
RELEASE_AUTOMATION_STATE_FILE = ROOT / "release-automation-state.json"
APPROVAL_INBOX_CLEARED_FILE = ROOT / "approval-inbox-cleared.json"
CONTINUITY_DIR = ROOT / "continuity"
CONTENT_EXPERIMENTS_FILE = ROOT / "content_experiments.json"
BRAND_BRAIN_FILE = ROOT / "brand_brain.json"
METRICS_GATHER_FILE = ROOT / "metrics-gather-results.json"
GROWTH_STATS_HISTORY_FILE = ROOT / "growth-stats-history.json"
AUTO_METRICS_STATE_FILE = ROOT / "automatic-metrics-state.json"
GROWTH_WEEKLY_REPORT_FILE = ROOT / "growth-weekly-report.json"
GROWTH_OPTIMIZER_FILE = ROOT / "growth-optimizer-plan.json"
INSTAGRAM_GROWTH_BLUEPRINT_FILE = ROOT / "instagram-growth-blueprint.json"
GROWTH_CONTROL_CENTER_FILE = ROOT / "growth-control-center.json"
COMMENT_ASSISTANT_FILE = ROOT / "comment-assistant.json"
COMMENT_GATHER_RAW_FILE = ROOT / "comment-gather-results.json"
COMMENT_REPLY_SCRIPT_FILE = ROOT / "prepare-comment-reply-playwright.js"
CHATGPT_CHAPTER_SCRIPT_FILE = ROOT / "create-chapter-chatgpt-playwright.js"
CHATGPT_CHAPTER_RESULT_FILE = ROOT / "chatgpt-chapter-result.json"
CHATGPT_CHAPTER_STATUS_FILE = ROOT / "chatgpt-chapter-status.json"
STORY_HOOK_SCRIPT_FILE = ROOT / "create-story-hook-chatgpt-playwright.js"
STORY_HOOK_RESULT_FILE = ROOT / "story-hook-chatgpt-result.json"
STORY_HOOK_STATUS_FILE = ROOT / "story-hook-video-status.json"
BROWSER_IMAGE_ASSIST_FILE = ROOT / "browser-image-assist.json"
BROWSER_IMAGE_ASSIST_SCRIPT_FILE = ROOT / "browser-image-assist-playwright.js"
GROWTH_AUTOMATION_FILE = ROOT / "growth-automation.json"
AUTOMATION_STRATEGY_FILE = ROOT / "automation-strategy.json"
GOOGLE_AI_IMAGE_USAGE_FILE = ROOT / "google-ai-image-usage.json"
YOUTUBE_POST_DRAFTS_FILE = ROOT / "youtube-post-drafts.json"
YOUTUBE_METADATA_EXPERIMENTS_FILE = ROOT / "youtube-metadata-experiments.json"
CREATOR_BENCHMARK_FILE = ROOT / "creator-benchmarks.json"
IMAGE_LAB_FILE = ROOT / "image-lab.json"
IMAGE_LAB_DIR = ROOT / "image-lab"
IMAGE_FEEDBACK_FILE = ROOT / "image-feedback.json"
TRAINING_DATA_DIR = ROOT / "training-data"
THUMBNAIL_TESTS_FILE = ROOT / "thumbnail-tests.json"
PINNED_ASSET_PLAN_FILE = ROOT / "pinned-profile-assets.json"
PINNED_ASSET_OUTPUT_DIR = ROOT / "pinned-profile-assets-output"
PREDICTIVE_GROWTH_PLAN_FILE = ROOT / "predictive-growth-plan.json"
CONVERSION_TRACKING_FILE = ROOT / "conversion-tracking.json"
PINNED_CONTENT_PLAN_FILE = ROOT / "pinned-content-plan.json"
PROFILE_AUDIT_FILE = ROOT / "profile-conversion-audit.json"
ARC_CAMPAIGN_FILE = ROOT / "arc-campaigns.json"
WEEKLY_AUTOPILOT_FILE = ROOT / "weekly-autopilot.json"
WEEKLY_GROWTH_SETTINGS_FILE = ROOT / "weekly-growth-settings.json"
CLICKUP_SYNC_FILE = ROOT / "clickup-sync.json"
CLICKUP_DEFAULT_LIST_NAME = "Web Novel Growth Hub"
APPROVAL_INBOX_CLEARED_FILE = ROOT / "approval-inbox-cleared.json"
POST_RECORDS_FILE = ROOT / "post-records.json"
KPI_SYNC_LOG_FILE = ROOT / "kpi-sync-log.json"
MONETIZATION_STATUS_FILE = ROOT / "monetization-status.json"
RECOVERY_LOG_FILE = ROOT / "recovery_log.json"
APP_TEST_REPORT_FILE = ROOT / "app-regression-dashboard.json"
PATREON_PENDING_DRAFT_FILE = ROOT / "patreon-draft-pending.json"
YOUTUBE_PENDING_UPLOAD_FILE = ROOT / "youtube-upload-pending.json"
YOUTUBE_COMMENT_QUEUE_FILE = ROOT / "youtube-comment-queue.json"
YOUTUBE_PINNED_COMMENT_VERIFIED_FILE = ROOT / "youtube-pinned-comment-verified.json"
YOUTUBE_LIBRARY_SCAN_FILE = ROOT / "youtube-library-scan.json"
YOUTUBE_LIBRARY_SCAN_SCRIPT_FILE = ROOT / "scan-youtube-library-playwright.js"
YOUTUBE_AUDIENCE_FIX_FILE = ROOT / "youtube-audience-fix-results.json"
YOUTUBE_AUDIENCE_FIX_SCRIPT_FILE = ROOT / "fix-youtube-audience-playwright.js"
YOUTUBE_COMMENT_PIN_SCRIPT_FILE = ROOT / "pin-youtube-comments-playwright.js"
YOUTUBE_COMMENT_PIN_RESULT_FILE = ROOT / "youtube-comment-pin-results.json"
YOUTUBE_END_SCREEN_PLAN_FILE = ROOT / "youtube-end-screen-plan.json"
YOUTUBE_END_SCREEN_SCRIPT_FILE = ROOT / "apply-youtube-end-screens-playwright.js"
YOUTUBE_END_SCREEN_RESULT_FILE = ROOT / "youtube-end-screen-results.json"
YOUTUBE_END_SCREEN_STATE_FILE = ROOT / "youtube-end-screen-state.json"
ROYAL_ROAD_GROWTH_FILE = ROOT / "royal-road-growth-tools.json"
DEEP_TIKTOK_ROTATION_FILE = ROOT / "deep-tiktok-rotation.json"

# --- LoRA style tracks (immutable definitions) ---
LORA_STYLE_TRACKS: dict[str, dict[str, str]] = {
    "main-posts": {
        "label": "Main Posts",
        "trigger": "azink_main",
        "promptSuffix": "Azure Inkblade chapter promo art, strong web novel cover composition, high-impact social media framing",
        "use": "Daily chapter promos, Patreon/X/Facebook images, and general novel campaign art.",
    },
    "comic-style": {
        "label": "Comic Style",
        "trigger": "azink_comic",
        "promptSuffix": "vertical manhwa webtoon panel style, expressive characters, cinematic sequential art, clean readable action",
        "use": "Deep TikTok, Shorts/Reels, story hooks, and comic-style chapter moments.",
    },
    "realistic-posts": {
        "label": "Realistic Posts",
        "trigger": "azink_real",
        "promptSuffix": "cinematic realistic fantasy photography, grounded lighting, detailed environment, dramatic character realism",
        "use": "Realistic promotional posts, darker story hook thumbnails, and non-comic experiments.",
    },
}

# --- Novel metadata ---
NOVEL_NAMES = {
    "EN": "Eternal Nexus",
    "HA": "Heavenly Ascension System",
    "SF": "Soulforge Era",
    "HP": "Hundredfold Path",
}
ROYAL_ROAD_URLS = {
    "EN": "https://www.royalroad.com/fiction/128852/eternal-nexus",
    "HA": "https://www.royalroad.com/fiction/130328/heavenly-ascension-system",
    "SF": "https://www.royalroad.com/fiction/129083/soulforge-era",
    "HP": "https://www.royalroad.com/fiction/128962/the-hundredfold-path",
}
ROYAL_ROAD_URLS_BY_NAME = {NOVEL_NAMES[abbr]: url for abbr, url in ROYAL_ROAD_URLS.items()}
DOCS_REPO_OWNER = "azureinkblade-ops"
DOCS_REPO_NAME = "Docs"
DOCS_NOVEL_FILES = {
    "EN": "Eternal Nexus - Updated Pass 1.docx",
    "HA": "Heavenly Ascension System.docx",
    "SF": "Soulforge Era - Revised.docx",
    "HP": "The Hundredfold Path - Updated Revision.docx",
}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CHAPTER_RELEASE_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
GENERAL_PROMO_DAYS = ["Tuesday", "Thursday", "Saturday"]

# --- Scheduling / thresholds ---
SCHEDULE_FILE = ROOT / "posting_schedule.json"
IMAGE_BANK_MINIMUM = int(os.environ.get("IMAGE_BANK_MINIMUM", "50"))
IMAGE_REUSE_COOLDOWN_DAYS = int(os.environ.get("IMAGE_REUSE_COOLDOWN_DAYS", "21"))
IMAGE_REUSE_MIN_BANK_PER_NOVEL = int(os.environ.get("IMAGE_REUSE_MIN_BANK_PER_NOVEL", "50"))
ALLOW_SAME_CHAPTER_IMAGE_REUSE = os.environ.get("ALLOW_SAME_CHAPTER_IMAGE_REUSE", "0").strip().lower() in {"1", "true", "yes", "on"}
YOUTUBE_MIDROLL_CTA = (
    "If this story has you listening this far, subscribe to Azure Inkblade so the next chapter "
    "finds you instead of getting buried. It helps us keep making more of these every week. "
    "Now, back to the chapter."
)
AUTO_METRICS_ENABLED = os.environ.get("AUTO_METRICS_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
AUTO_METRICS_MIN_AGE_HOURS = max(1, int(os.environ.get("AUTO_METRICS_MIN_AGE_HOURS", "36")))
AUTO_METRICS_INTERVAL_HOURS = max(1, int(os.environ.get("AUTO_METRICS_INTERVAL_HOURS", "24")))
AUTO_METRICS_RETRY_HOURS = max(1, int(os.environ.get("AUTO_METRICS_RETRY_HOURS", "2")))
COMMENT_ASSISTANT_AUTO_ENABLED = os.environ.get("COMMENT_ASSISTANT_AUTO_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
COMMENT_ASSISTANT_INTERVAL_HOURS = max(1, int(os.environ.get("COMMENT_ASSISTANT_INTERVAL_HOURS", "24")))

# --- External paid AI (OpenAI + Google Gemini) disabled by default ---
# No API credits configured, so local/fallback paths fire instantly instead of
# burning quota on a network round-trip + 429. Set ENABLE_EXTERNAL_AI=1 to re-enable.
EXTERNAL_AI_ENABLED = os.environ.get("ENABLE_EXTERNAL_AI", "0").strip() == "1"

# --- Hand / regional repair (EA4F-1) ---
# Off by default. Enable only after mask + backend path is verified.
HAND_REPAIR_ENABLED = os.environ.get("HAND_REPAIR_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
HAND_REPAIR_AUTO_ACCEPT = os.environ.get("HAND_REPAIR_AUTO_ACCEPT", "0").strip().lower() in {"1", "true", "yes", "on"}

# --- Pose ControlNet (EA4F-2) ---
# When on, create_prompt_fallback_image may attach ControlNet kwargs from the
# remembered Visual Director shot plan (or prompt heuristic). Default off.
POSE_CONTROLNET_ENABLED = os.environ.get("POSE_CONTROLNET_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}

# --- Hand repair auto-mask stub (EA4F-1) ---
HAND_REPAIR_AUTO_MASK = os.environ.get("HAND_REPAIR_AUTO_MASK", "0").strip().lower() in {"1", "true", "yes", "on"}
