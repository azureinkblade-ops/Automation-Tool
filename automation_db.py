from __future__ import annotations

import json
import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

try:
    import orjson
except Exception:  # pragma: no cover - optional speed path
    orjson = None

try:
    from pydantic import BaseModel, ConfigDict
except Exception:  # pragma: no cover - app can still run without pydantic
    BaseModel = None
    ConfigDict = None


DB_FILENAME = "automation_state.db"
SCHEMA_VERSION = 8
_LOCK = threading.RLock()

DEFAULT_NOVELS = {
    "EN": "Eternal Nexus",
    "HA": "Heavenly Ascension System",
    "SF": "Soul Forge Era",
    "HP": "Hundredfold Path",
}

DEFAULT_ROYAL_ROAD_URLS = {
    "EN": "https://www.royalroad.com/fiction/128852/eternal-nexus",
    "HA": "https://www.royalroad.com/fiction/130328/heavenly-ascension-system",
    "SF": "https://www.royalroad.com/fiction/129083/soulforge-era",
    "HP": "https://www.royalroad.com/fiction/128962/the-hundredfold-path",
}

DEFAULT_SOCIAL_URLS = {
    "patreon": "https://www.patreon.com/c/azureinkblade",
    "youtube": "https://www.youtube.com/@AzureInkblade",
    "tiktok": "https://www.tiktok.com/@azureinkblade",
    "x": "https://x.com/azureinkblade",
}


if BaseModel:
    class PostRecordModel(BaseModel):
        model_config = ConfigDict(extra="allow")

        automationRecordId: str
        clickupTaskId: str = ""
        novel: str = ""
        chapter: str = ""
        platform: str = ""
        contentType: str = ""
        publishDate: str = ""
        liveUrl: str = ""
        bufferPostId: str = ""
        assetFolder: str = ""
        localPath: str = ""
        title: str = ""
        status: str = ""
else:
    PostRecordModel = None


def db_path(root: Path) -> Path:
    return Path(root) / DB_FILENAME


def utc_now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def dumps_json(value: Any) -> str:
    if orjson:
        return orjson.dumps(value, option=orjson.OPT_INDENT_2).decode("utf-8")
    return json.dumps(value, indent=2, ensure_ascii=False)


def loads_json(value: str) -> Any:
    if not value:
        return None
    if orjson:
        return orjson.loads(value)
    return json.loads(value)


def normalize_abbr(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    upper = raw.upper()
    if upper in DEFAULT_NOVELS:
        return upper
    lowered = raw.lower()
    for abbr, title in DEFAULT_NOVELS.items():
        if lowered == title.lower() or lowered in title.lower():
            return abbr
    aliases = {
        "ETERNAL_NEXUS": "EN",
        "HEAVENLY_ASCENSION_SYSTEM": "HA",
        "SOULFORGE": "SF",
        "SOUL_FORGE": "SF",
        "SOUL_FORGE_ERA": "SF",
        "HUNDREDFOLD_PATH": "HP",
        "THE_HUNDREDFOLD_PATH": "HP",
    }
    return aliases.get(upper.replace(" ", "_").replace("-", "_"), upper[:12])


def int_or_none(value: Any) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    return 1 if str(value or "").strip().lower() in {"1", "true", "yes", "y", "done", "posted", "exists"} else 0


def stable_id(*parts: Any) -> str:
    text = "|".join(str(part or "").strip().lower() for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def make_chapter_id(abbr: Any, chapter: Any) -> str:
    novel_id = normalize_abbr(abbr)
    chapter_number = int_or_none(chapter) or 0
    return f"{novel_id}-{chapter_number}" if novel_id and chapter_number else ""


def make_platform_account_id(platform: Any, handle: Any = "") -> str:
    platform_text = str(platform or "").strip().lower()
    handle_text = str(handle or "azureinkblade").strip().lower()
    return f"{platform_text}:{handle_text}" if platform_text else ""


def infer_chapter_status(entry: dict[str, Any]) -> str:
    if bool_int(entry.get("royalRoadPosted") or entry.get("postedToRoyalRoad") or entry.get("royalRoadExists")):
        return "royal_road_live"
    if bool_int(entry.get("patreonPosted") or entry.get("postedToPatreon") or entry.get("patreonInnerExists")):
        return "patreon_scheduled"
    if bool_int(entry.get("githubUploaded") or entry.get("uploadedToGitHub") or entry.get("written")):
        return "github_uploaded"
    if bool_int(entry.get("promoPackBuilt") or entry.get("shortsBuilt") or entry.get("youtubeBuilt")):
        return "assets_built"
    return str(entry.get("status") or "tracked")


def infer_asset_type(record: dict[str, Any]) -> str:
    content_type = str(record.get("contentType") or record.get("content_type") or "").lower()
    platform = str(record.get("platform") or "").lower()
    path_text = str(record.get("localPath") or record.get("assetFolder") or "").lower()
    if "youtube" in content_type and "short" not in content_type:
        return "youtube_video"
    if "short" in content_type or "tiktok" in platform or "reel" in content_type:
        return "short_video" if path_text.endswith(".mp4") or "video" in path_text else "short_pack"
    if any(token in content_type for token in ["image", "social", "daily", "campaign"]):
        return "promo_image"
    return "asset_folder"


def connect(root: Path) -> sqlite3.Connection:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(root: Path) -> Path:
    with _LOCK:
        with connect(root) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS post_records (
                    automation_record_id TEXT PRIMARY KEY,
                    clickup_task_id TEXT,
                    novel TEXT,
                    chapter TEXT,
                    platform TEXT,
                    content_type TEXT,
                    publish_date TEXT,
                    live_url TEXT,
                    buffer_post_id TEXT,
                    asset_folder TEXT,
                    local_path TEXT,
                    title TEXT,
                    status TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_post_records_lookup
                    ON post_records(novel, chapter, platform, content_type, publish_date);

                CREATE TABLE IF NOT EXISTS chapter_ledger (
                    ledger_key TEXT PRIMARY KEY,
                    abbr TEXT NOT NULL,
                    chapter INTEGER NOT NULL,
                    novel TEXT,
                    title TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chapter_ledger_path
                    ON chapter_ledger(abbr, chapter);

                CREATE TABLE IF NOT EXISTS release_status (
                    status_key TEXT PRIMARY KEY,
                    abbr TEXT,
                    chapter INTEGER,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_release_status_path
                    ON release_status(abbr, chapter);

                CREATE TABLE IF NOT EXISTS approval_cleared (
                    approval_key TEXT PRIMARY KEY,
                    kind TEXT,
                    abbr TEXT,
                    chapter TEXT,
                    platform TEXT,
                    folder TEXT,
                    comment_id TEXT,
                    reason TEXT,
                    payload_json TEXT NOT NULL,
                    cleared_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_approval_cleared_kind
                    ON approval_cleared(kind, abbr, chapter, platform);

                CREATE TABLE IF NOT EXISTS recovery_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_hash TEXT,
                    step TEXT,
                    error_type TEXT,
                    abbr TEXT,
                    chapter TEXT,
                    folder TEXT,
                    reason TEXT,
                    retry_path TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_recovery_events_path
                    ON recovery_events(abbr, chapter, error_type);

                CREATE TABLE IF NOT EXISTS state_snapshots (
                    state_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS novels (
                    novel_id TEXT PRIMARY KEY,
                    abbr TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    royal_road_url TEXT,
                    patreon_url TEXT,
                    youtube_playlist_url TEXT,
                    status TEXT DEFAULT 'active',
                    current_daily_chapter INTEGER,
                    current_upload_chapter INTEGER,
                    current_youtube_chapter INTEGER,
                    current_variant_chapter INTEGER,
                    created_at TEXT,
                    updated_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS novel_chapters (
                    chapter_id TEXT PRIMARY KEY,
                    novel_id TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
                    chapter_number INTEGER NOT NULL,
                    chapter_label TEXT,
                    title TEXT,
                    github_path TEXT,
                    github_sha TEXT,
                    content_hash TEXT,
                    word_count INTEGER,
                    status TEXT,
                    inner_disciple_date TEXT,
                    path_initiate_date TEXT,
                    royal_road_date TEXT,
                    patreon_inner_exists INTEGER DEFAULT 0,
                    patreon_path_exists INTEGER DEFAULT 0,
                    royal_road_exists INTEGER DEFAULT 0,
                    royal_road_chapter_url TEXT,
                    royal_road_edit_url TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(novel_id, chapter_number)
                );

                CREATE INDEX IF NOT EXISTS idx_novel_chapters_novel_number
                    ON novel_chapters(novel_id, chapter_number);

                CREATE TABLE IF NOT EXISTS chapter_assets (
                    asset_id TEXT PRIMARY KEY,
                    chapter_id TEXT REFERENCES novel_chapters(chapter_id) ON DELETE SET NULL,
                    novel_id TEXT REFERENCES novels(novel_id) ON DELETE SET NULL,
                    asset_type TEXT NOT NULL,
                    platform_target TEXT,
                    local_path TEXT,
                    public_url TEXT,
                    folder TEXT,
                    content_hash TEXT,
                    image_score REAL,
                    approved INTEGER DEFAULT 0,
                    rejected INTEGER DEFAULT 0,
                    rejection_reason TEXT,
                    provider TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_chapter_assets_chapter_type
                    ON chapter_assets(chapter_id, asset_type);
                CREATE INDEX IF NOT EXISTS idx_chapter_assets_hash
                    ON chapter_assets(content_hash);

                CREATE TABLE IF NOT EXISTS platform_accounts (
                    platform_account_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    display_name TEXT,
                    handle TEXT,
                    profile_url TEXT,
                    buffer_channel_id TEXT,
                    enabled INTEGER DEFAULT 1,
                    supports_api_publish INTEGER DEFAULT 0,
                    supports_browser_publish INTEGER DEFAULT 1,
                    supports_metrics INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS platform_posts (
                    post_id TEXT PRIMARY KEY,
                    automation_record_id TEXT UNIQUE NOT NULL,
                    novel_id TEXT REFERENCES novels(novel_id) ON DELETE SET NULL,
                    chapter_id TEXT REFERENCES novel_chapters(chapter_id) ON DELETE SET NULL,
                    platform_account_id TEXT REFERENCES platform_accounts(platform_account_id) ON DELETE SET NULL,
                    platform TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    campaign_type TEXT,
                    caption_status TEXT,
                    scheduling_status TEXT,
                    publish_date TEXT,
                    scheduled_at TEXT,
                    published_at TEXT,
                    live_url TEXT,
                    buffer_post_id TEXT,
                    clickup_task_id TEXT,
                    asset_folder TEXT,
                    primary_asset_id TEXT,
                    variant_group_id TEXT,
                    variant_label TEXT,
                    failure_reason TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_platform_posts_lookup
                    ON platform_posts(novel_id, chapter_id, platform, content_type);
                CREATE INDEX IF NOT EXISTS idx_platform_posts_status
                    ON platform_posts(platform, scheduling_status);
                CREATE INDEX IF NOT EXISTS idx_platform_posts_publish_date
                    ON platform_posts(publish_date);
                CREATE INDEX IF NOT EXISTS idx_platform_posts_clickup
                    ON platform_posts(clickup_task_id);

                CREATE TABLE IF NOT EXISTS youtube_posts (
                    post_id TEXT PRIMARY KEY REFERENCES platform_posts(post_id) ON DELETE CASCADE,
                    youtube_video_id TEXT,
                    youtube_kind TEXT,
                    title TEXT,
                    description TEXT,
                    thumbnail_asset_id TEXT REFERENCES chapter_assets(asset_id) ON DELETE SET NULL,
                    made_for_kids INTEGER DEFAULT 0,
                    pinned_comment_status TEXT,
                    end_screen_status TEXT,
                    playlist_status TEXT,
                    upload_status TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS tiktok_posts (
                    post_id TEXT PRIMARY KEY REFERENCES platform_posts(post_id) ON DELETE CASCADE,
                    video_asset_id TEXT REFERENCES chapter_assets(asset_id) ON DELETE SET NULL,
                    sound_asset_id TEXT REFERENCES chapter_assets(asset_id) ON DELETE SET NULL,
                    duration_seconds REAL,
                    overlay_status TEXT,
                    deep_tiktok INTEGER DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS instagram_posts (
                    post_id TEXT PRIMARY KEY REFERENCES platform_posts(post_id) ON DELETE CASCADE,
                    instagram_kind TEXT,
                    image_asset_id TEXT REFERENCES chapter_assets(asset_id) ON DELETE SET NULL,
                    video_asset_id TEXT REFERENCES chapter_assets(asset_id) ON DELETE SET NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS facebook_posts (
                    post_id TEXT PRIMARY KEY REFERENCES platform_posts(post_id) ON DELETE CASCADE,
                    facebook_kind TEXT,
                    browser_draft_status TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS x_posts (
                    post_id TEXT PRIMARY KEY REFERENCES platform_posts(post_id) ON DELETE CASCADE,
                    character_count INTEGER,
                    browser_draft_status TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS patreon_posts (
                    post_id TEXT PRIMARY KEY REFERENCES platform_posts(post_id) ON DELETE CASCADE,
                    tier TEXT,
                    scheduled_for TEXT,
                    draft_url TEXT,
                    browser_draft_status TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS royal_road_posts (
                    post_id TEXT PRIMARY KEY REFERENCES platform_posts(post_id) ON DELETE CASCADE,
                    chapter_id TEXT REFERENCES novel_chapters(chapter_id) ON DELETE SET NULL,
                    edit_url TEXT,
                    diff_status TEXT,
                    author_note_status TEXT,
                    browser_draft_status TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS release_plan_rows (
                    release_plan_id TEXT PRIMARY KEY,
                    novel_id TEXT NOT NULL REFERENCES novels(novel_id) ON DELETE CASCADE,
                    novel_abbr TEXT NOT NULL,
                    chapter_number INTEGER NOT NULL,
                    chapter_title TEXT,
                    chapter_source_path TEXT,
                    inner_disciple_date TEXT NOT NULL,
                    path_initiate_date TEXT NOT NULL,
                    royal_road_date TEXT NOT NULL,
                    patreon_inner_status TEXT DEFAULT 'planned',
                    patreon_path_status TEXT DEFAULT 'planned',
                    royal_road_status TEXT DEFAULT 'planned',
                    last_prepared_at TEXT,
                    last_error TEXT,
                    notes TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(novel_abbr, chapter_number)
                );

                CREATE INDEX IF NOT EXISTS idx_release_plan_rows_dates
                    ON release_plan_rows(inner_disciple_date, path_initiate_date, royal_road_date);
                CREATE INDEX IF NOT EXISTS idx_release_plan_rows_lookup
                    ON release_plan_rows(novel_abbr, chapter_number);

                CREATE TABLE IF NOT EXISTS release_automation_jobs (
                    job_id TEXT PRIMARY KEY,
                    job_key TEXT UNIQUE NOT NULL,
                    release_plan_id TEXT,
                    novel_abbr TEXT NOT NULL,
                    chapter_number INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    worker_id TEXT,
                    next_attempt_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    verified_at TEXT,
                    remote_url TEXT,
                    last_error TEXT,
                    screenshot_path TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_release_automation_jobs_work
                    ON release_automation_jobs(status, next_attempt_at, scheduled_for);
                CREATE INDEX IF NOT EXISTS idx_release_automation_jobs_chapter
                    ON release_automation_jobs(novel_abbr, chapter_number, stage);

                CREATE TABLE IF NOT EXISTS platform_post_metrics (
                    metric_id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL REFERENCES platform_posts(post_id) ON DELETE CASCADE,
                    platform TEXT NOT NULL,
                    window TEXT NOT NULL,
                    source TEXT,
                    collected_at TEXT NOT NULL,
                    views INTEGER,
                    impressions INTEGER,
                    engagements INTEGER,
                    engagement_rate REAL,
                    result TEXT,
                    notes TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    style_track TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_platform_post_metrics_lookup
                    ON platform_post_metrics(post_id, window);

                CREATE TABLE IF NOT EXISTS platform_post_actions (
                    action_id TEXT PRIMARY KEY,
                    post_id TEXT REFERENCES platform_posts(post_id) ON DELETE CASCADE,
                    action_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    platform TEXT,
                    reason TEXT,
                    retry_after TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_platform_post_actions_lookup
                    ON platform_post_actions(post_id, action_type, created_at);

                CREATE TABLE IF NOT EXISTS social_stats_daily (
                    stat_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    collected_date TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_social_stats_daily_lookup
                    ON social_stats_daily(platform, channel, collected_date);

                CREATE TABLE IF NOT EXISTS weekly_growth_plans (
                    plan_id TEXT PRIMARY KEY,
                    week_start TEXT NOT NULL UNIQUE,
                    week_end TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    weights_json TEXT NOT NULL DEFAULT '{}',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS weekly_growth_slots (
                    slot_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL REFERENCES weekly_growth_plans(plan_id) ON DELETE CASCADE,
                    slot_number INTEGER NOT NULL,
                    slot_date TEXT NOT NULL,
                    day_name TEXT NOT NULL,
                    slot_type TEXT NOT NULL,
                    novel_abbr TEXT,
                    chapter_number INTEGER,
                    engagement_goal TEXT NOT NULL,
                    predicted_score REAL NOT NULL,
                    quality_status TEXT NOT NULL,
                    delivery_status TEXT NOT NULL DEFAULT 'ready',
                    hook_fingerprint TEXT,
                    cta_fingerprint TEXT,
                    image_fingerprint TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(plan_id, slot_number)
                );

                CREATE INDEX IF NOT EXISTS idx_weekly_growth_slots_plan
                    ON weekly_growth_slots(plan_id, slot_number);
                CREATE INDEX IF NOT EXISTS idx_weekly_growth_slots_history
                    ON weekly_growth_slots(slot_date, novel_abbr, engagement_goal);

                -- === Slice 1 (AIVSB retrieval index): additive, derived cache only ===
                -- Handoff: SLICE1-AUTOMATION-DB-HANDOFF (recorded 2026-07-27).
                -- These tables are DERIVED from the external AIVSB YAML corpus and may be
                -- dropped/rebuilt at any time. No SCHEMA_VERSION bump; idempotent migration.
                --
                -- SCHEMA_VERSION CONVENTION (explicit, per handoff): SCHEMA_VERSION governs
                -- canonical feature tables. Additive CREATE TABLE IF NOT EXISTS for OPTIONAL
                -- DERIVED CACHES does NOT advance SCHEMA_VERSION. These tables are rebuildable
                -- and carry no canonical data, so a future reader must not infer schema "6"
                -- includes or excludes them — the handoff record is the authority.
                CREATE TABLE IF NOT EXISTS retrieval_chunks (
                    chunk_id      TEXT PRIMARY KEY,
                    novel_id      TEXT NOT NULL,
                    domain        TEXT NOT NULL,
                    character_id  TEXT,
                    platform      TEXT,
                    asset_type    TEXT,
                    status        TEXT NOT NULL,
                    version       TEXT,
                    content_hash  TEXT NOT NULL,
                    summary       TEXT,
                    body          TEXT NOT NULL,
                    tags          TEXT,
                    source_file   TEXT NOT NULL,
                    chunk_path    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunk_embeddings (
                    chunk_id            TEXT PRIMARY KEY REFERENCES retrieval_chunks(chunk_id) ON DELETE CASCADE,
                    embedding_model     TEXT NOT NULL,
                    embedding_revision  TEXT,
                    embedding_dim       INTEGER NOT NULL,
                    embedded_at         TEXT NOT NULL,
                    content_hash        TEXT NOT NULL,
                    vector              BLOB NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_rc_novel_domain ON retrieval_chunks(novel_id, domain);
                CREATE INDEX IF NOT EXISTS idx_rc_char        ON retrieval_chunks(character_id);
                CREATE INDEX IF NOT EXISTS idx_rc_platform     ON retrieval_chunks(platform);
                CREATE INDEX IF NOT EXISTS idx_rc_status      ON retrieval_chunks(status);
                CREATE INDEX IF NOT EXISTS idx_ce_model        ON chunk_embeddings(embedding_model);

                -- === Slice 1 provenance follow-up (AIVSB-RETRIEVAL-PROVENANCE handoff) ===
                -- Durable governance/audit metadata (NOT a rebuildable derived cache).
                -- SCHEMA_VERSION advanced 6 -> 7 for these tables (see handoff rationale).
                CREATE TABLE IF NOT EXISTS retrieval_index_runs (
                    run_id             TEXT PRIMARY KEY,
                    canonical_repo_root TEXT NOT NULL,
                    source_git_commit TEXT,
                    source_git_dirty  INTEGER NOT NULL DEFAULT 0,
                    extractor_version TEXT NOT NULL,
                    embedding_model   TEXT,
                    embedding_revision TEXT,
                    manifest_hash      TEXT NOT NULL,
                    chunk_count        INTEGER NOT NULL,
                    embedding_count    INTEGER NOT NULL,
                    started_at         TEXT NOT NULL,
                    completed_at       TEXT,
                    status             TEXT NOT NULL,
                    error_message      TEXT
                );

                CREATE TABLE IF NOT EXISTS retrieval_index_run_chunks (
                    run_id       TEXT NOT NULL,
                    chunk_id     TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    PRIMARY KEY (run_id, chunk_id),
                    FOREIGN KEY (run_id)
                        REFERENCES retrieval_index_runs(run_id)
                        ON DELETE CASCADE
                );

                -- Agent post lifecycle (Hermes post-differentiation). Source of truth
                -- for every attempt, success or failure. Additive (schema 7 -> 8).
                CREATE TABLE IF NOT EXISTS agent_post_runs (
                    run_id            TEXT PRIMARY KEY,
                    novel             TEXT,
                    chapter           TEXT,
                    title             TEXT,
                    status            TEXT NOT NULL,
                    fallback_reason   TEXT,
                    hermes_profile    TEXT,
                    provider          TEXT,
                    model             TEXT,
                    command_flags     TEXT,
                    request_text      TEXT,
                    decoded_stdout    TEXT,
                    raw_stdout        BLOB,
                    stderr_text       TEXT,
                    selected_final_block TEXT,
                    hook              TEXT,
                    caption           TEXT,
                    cta               TEXT,
                    content_angle     TEXT,
                    intended_audience TEXT,
                    schema_version    TEXT DEFAULT 'social-post-v1',
                    parse_mode        TEXT,
                    validation_errors TEXT,
                    started_at        TEXT,
                    completed_at      TEXT,
                    duration_ms       INTEGER,
                    exit_code         INTEGER,
                    created_at        TEXT
                );

                CREATE TABLE IF NOT EXISTS agent_post_fields (
                    run_id    TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    field    TEXT NOT NULL,
                    value    TEXT,
                    PRIMARY KEY (run_id, position),
                    FOREIGN KEY (run_id)
                        REFERENCES agent_post_runs(run_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_post_hashtags (
                    run_id    TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    tag      TEXT NOT NULL,
                    PRIMARY KEY (run_id, position),
                    FOREIGN KEY (run_id)
                        REFERENCES agent_post_runs(run_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS generated_social_posts (
                    run_id     TEXT NOT NULL,
                    platform   TEXT NOT NULL,
                    post_text  TEXT,
                    agent_used INTEGER NOT NULL DEFAULT 0,
                    fallback_reason TEXT,
                    PRIMARY KEY (run_id, platform),
                    FOREIGN KEY (run_id)
                        REFERENCES agent_post_runs(run_id)
                        ON DELETE CASCADE
                );
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(recovery_events)").fetchall()
            }
            if "event_hash" not in columns:
                conn.execute("ALTER TABLE recovery_events ADD COLUMN event_hash TEXT")
                rows = conn.execute("SELECT id, payload_json FROM recovery_events").fetchall()
                seen: set[str] = set()
                for row in rows:
                    event_hash = hashlib.sha256(str(row["payload_json"] or "").encode("utf-8")).hexdigest()
                    if event_hash in seen:
                        conn.execute("DELETE FROM recovery_events WHERE id=?", (row["id"],))
                    else:
                        seen.add(event_hash)
                        conn.execute("UPDATE recovery_events SET event_hash=? WHERE id=?", (event_hash, row["id"]))
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_recovery_events_hash ON recovery_events(event_hash)")
            # F: capture which LoRA style track a post used, so we can compare style performance.
            metrics_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(platform_post_metrics)").fetchall()
            }
            if "style_track" not in metrics_columns:
                conn.execute("ALTER TABLE platform_post_metrics ADD COLUMN style_track TEXT")
            now = utc_now_text()
            conn.execute(
                """
                INSERT INTO app_meta(key, value, updated_at)
                VALUES('schemaVersion', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (str(SCHEMA_VERSION), now),
            )
            conn.commit()
    return db_path(root)


def record_post_style_track(root: Path, post_id: str, style_track: str, platform: str | None = None) -> None:
    """F: persist which LoRA style track a post used, so style performance can be compared later.
    Writes into platform_post_metrics (one row per post, window='style') if not already present.
    """
    if not style_track:
        return
    with _LOCK, sqlite3.connect(db_path(root)) as conn:
        conn.execute(
            """
            INSERT INTO platform_post_metrics
                (metric_id, post_id, platform, window, source, collected_at, style_track, payload_json)
            VALUES (?, ?, ?, 'style', 'pack_metadata', ?, ?, ?)
            ON CONFLICT(metric_id) DO UPDATE SET style_track=excluded.style_track
            """,
            (f"style:{post_id}", post_id, platform, utc_now_text(), style_track, json.dumps({"style_track": style_track})),
        )
        conn.commit()


def backfill_style_tracks_from_packs(root: Path) -> int:
    """F: scan tiktok-posts/*/metadata.json for pack_track and write style_track rows.
    Returns the number of packs backfilled. Idempotent (uses ON CONFLICT by metric_id).
    """
    count = 0
    tiktok_dir = root / "tiktok-posts"
    if not tiktok_dir.exists():
        return 0
    for meta in tiktok_dir.glob("*/metadata.json"):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        pack_track = data.get("pack_track") or data.get("style_track")
        if not pack_track:
            continue
        post_id = f"{data.get('abbr','')}-{data.get('chapter','')}-{meta.parent.name}"
        record_post_style_track(root, post_id, pack_track, platform="tiktok")
        count += 1
    return count


def ensure_default_novels(
    root: Path,
    novel_names: dict[str, str] | None = None,
    royal_road_urls: dict[str, str] | None = None,
) -> int:
    names = dict(DEFAULT_NOVELS)
    if novel_names:
        names.update({normalize_abbr(k): str(v) for k, v in novel_names.items() if normalize_abbr(k)})
    rr_urls = dict(DEFAULT_ROYAL_ROAD_URLS)
    if royal_road_urls:
        rr_urls.update({normalize_abbr(k): str(v) for k, v in royal_road_urls.items() if normalize_abbr(k)})
    now = utc_now_text()
    init_db(root)
    count = 0
    with _LOCK:
        with connect(root) as conn:
            for abbr, title in names.items():
                if not abbr:
                    continue
                payload = {
                    "abbr": abbr,
                    "title": title,
                    "royalRoadUrl": rr_urls.get(abbr, ""),
                    "patreonUrl": DEFAULT_SOCIAL_URLS["patreon"],
                    "youtubeUrl": DEFAULT_SOCIAL_URLS["youtube"],
                }
                conn.execute(
                    """
                    INSERT INTO novels(
                        novel_id, abbr, title, royal_road_url, patreon_url, status,
                        payload_json, created_at, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, 'active', ?, ?, ?)
                    ON CONFLICT(novel_id) DO UPDATE SET
                        abbr=excluded.abbr,
                        title=excluded.title,
                        royal_road_url=COALESCE(NULLIF(excluded.royal_road_url, ''), novels.royal_road_url),
                        patreon_url=COALESCE(NULLIF(excluded.patreon_url, ''), novels.patreon_url),
                        updated_at=excluded.updated_at,
                        payload_json=excluded.payload_json
                    """,
                    (
                        abbr,
                        abbr,
                        title,
                        rr_urls.get(abbr, ""),
                        DEFAULT_SOCIAL_URLS["patreon"],
                        dumps_json(payload),
                        now,
                        now,
                    ),
                )
                count += 1
            conn.commit()
    return count


def ensure_platform_account(root: Path, platform: str, *, handle: str = "azureinkblade", buffer_channel_id: str = "") -> str:
    platform_text = str(platform or "").strip().lower()
    if not platform_text:
        return ""
    account_id = make_platform_account_id(platform_text, handle)
    url_by_platform = {
        "patreon": DEFAULT_SOCIAL_URLS["patreon"],
        "youtube": DEFAULT_SOCIAL_URLS["youtube"],
        "tiktok": DEFAULT_SOCIAL_URLS["tiktok"],
        "instagram": "https://www.instagram.com/azureinkblade",
        "facebook": "",
        "x": DEFAULT_SOCIAL_URLS["x"],
        "royal_road": "",
        "royalroad": "",
        "buffer": "",
    }
    now = utc_now_text()
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO platform_accounts(
                    platform_account_id, platform, display_name, handle, profile_url,
                    buffer_channel_id, enabled, supports_api_publish, supports_browser_publish,
                    supports_metrics, payload_json, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform_account_id) DO UPDATE SET
                    buffer_channel_id=COALESCE(NULLIF(excluded.buffer_channel_id, ''), platform_accounts.buffer_channel_id),
                    updated_at=excluded.updated_at,
                    payload_json=excluded.payload_json
                """,
                (
                    account_id,
                    platform_text,
                    "Azure Inkblade",
                    handle,
                    url_by_platform.get(platform_text, ""),
                    buffer_channel_id,
                    1 if platform_text in {"youtube", "tiktok", "instagram"} else 0,
                    1 if platform_text in {"patreon", "royal_road", "royalroad", "x", "facebook", "youtube"} else 0,
                    1 if platform_text in {"youtube", "tiktok", "instagram", "facebook"} else 0,
                    dumps_json({"platform": platform_text, "handle": handle}),
                    now,
                    now,
                ),
            )
            conn.commit()
    return account_id


def upsert_novel_chapter_from_ledger(root: Path, entry: dict[str, Any]) -> str:
    abbr = normalize_abbr(entry.get("abbr") or entry.get("novel"))
    chapter = int_or_none(entry.get("chapter") or entry.get("chapterNumber") or entry.get("chapter_number"))
    if not abbr or not chapter:
        return ""
    ensure_default_novels(root)
    chapter_id = make_chapter_id(abbr, chapter)
    now = str(entry.get("updatedAt") or utc_now_text())
    title = str(entry.get("title") or entry.get("chapterTitle") or "").strip()
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO novel_chapters(
                    chapter_id, novel_id, chapter_number, chapter_label, title, github_path,
                    github_sha, content_hash, word_count, status, inner_disciple_date,
                    path_initiate_date, royal_road_date, patreon_inner_exists,
                    patreon_path_exists, royal_road_exists, royal_road_chapter_url,
                    royal_road_edit_url, payload_json, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter_id) DO UPDATE SET
                    title=COALESCE(NULLIF(excluded.title, ''), novel_chapters.title),
                    github_path=COALESCE(NULLIF(excluded.github_path, ''), novel_chapters.github_path),
                    github_sha=COALESCE(NULLIF(excluded.github_sha, ''), novel_chapters.github_sha),
                    content_hash=COALESCE(NULLIF(excluded.content_hash, ''), novel_chapters.content_hash),
                    word_count=COALESCE(excluded.word_count, novel_chapters.word_count),
                    status=COALESCE(NULLIF(excluded.status, ''), novel_chapters.status),
                    inner_disciple_date=COALESCE(NULLIF(excluded.inner_disciple_date, ''), novel_chapters.inner_disciple_date),
                    path_initiate_date=COALESCE(NULLIF(excluded.path_initiate_date, ''), novel_chapters.path_initiate_date),
                    royal_road_date=COALESCE(NULLIF(excluded.royal_road_date, ''), novel_chapters.royal_road_date),
                    patreon_inner_exists=MAX(novel_chapters.patreon_inner_exists, excluded.patreon_inner_exists),
                    patreon_path_exists=MAX(novel_chapters.patreon_path_exists, excluded.patreon_path_exists),
                    royal_road_exists=MAX(novel_chapters.royal_road_exists, excluded.royal_road_exists),
                    royal_road_chapter_url=COALESCE(NULLIF(excluded.royal_road_chapter_url, ''), novel_chapters.royal_road_chapter_url),
                    royal_road_edit_url=COALESCE(NULLIF(excluded.royal_road_edit_url, ''), novel_chapters.royal_road_edit_url),
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    chapter_id,
                    abbr,
                    chapter,
                    str(entry.get("chapterLabel") or entry.get("label") or f"Chapter {chapter}"),
                    title,
                    str(entry.get("githubPath") or entry.get("path") or ""),
                    str(entry.get("githubSha") or entry.get("sha") or ""),
                    str(entry.get("contentHash") or entry.get("hash") or ""),
                    int_or_none(entry.get("wordCount") or entry.get("words")),
                    infer_chapter_status(entry),
                    str(entry.get("innerDiscipleDate") or entry.get("inner_disciple_date") or ""),
                    str(entry.get("pathInitiateDate") or entry.get("path_initiate_date") or ""),
                    str(entry.get("royalRoadDate") or entry.get("royal_road_date") or ""),
                    bool_int(entry.get("patreonInnerExists") or entry.get("innerExists")),
                    bool_int(entry.get("patreonPathExists") or entry.get("pathExists")),
                    bool_int(entry.get("royalRoadExists") or entry.get("rrExists")),
                    str(entry.get("royalRoadChapterUrl") or entry.get("royalRoadUrl") or ""),
                    str(entry.get("royalRoadEditUrl") or entry.get("editUrl") or ""),
                    dumps_json(entry),
                    now,
                    now,
                ),
            )
            conn.commit()
    return chapter_id


def upsert_chapter_asset(root: Path, asset: dict[str, Any]) -> str:
    abbr = normalize_abbr(asset.get("novel") or asset.get("abbr"))
    if abbr not in DEFAULT_NOVELS:
        abbr = ""
    chapter = int_or_none(asset.get("chapter"))
    chapter_id = make_chapter_id(abbr, chapter) if abbr and chapter else ""
    if chapter_id:
        upsert_novel_chapter_from_ledger(root, {"abbr": abbr, "chapter": chapter, "title": asset.get("title") or ""})
    elif abbr:
        ensure_default_novels(root)
    local_path = str(asset.get("localPath") or asset.get("path") or asset.get("assetFolder") or "").strip()
    folder = str(asset.get("folder") or asset.get("assetFolder") or "").strip()
    asset_type = str(asset.get("assetType") or asset.get("type") or "asset_folder").strip()
    if not local_path and not folder:
        return ""
    asset_id = str(asset.get("assetId") or stable_id("asset", chapter_id, abbr, asset_type, local_path, folder))
    now = str(asset.get("updatedAt") or asset.get("createdAt") or utc_now_text())
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO chapter_assets(
                    asset_id, chapter_id, novel_id, asset_type, platform_target, local_path,
                    public_url, folder, content_hash, image_score, approved, rejected,
                    rejection_reason, provider, payload_json, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    chapter_id=COALESCE(excluded.chapter_id, chapter_assets.chapter_id),
                    novel_id=COALESCE(excluded.novel_id, chapter_assets.novel_id),
                    platform_target=COALESCE(NULLIF(excluded.platform_target, ''), chapter_assets.platform_target),
                    local_path=COALESCE(NULLIF(excluded.local_path, ''), chapter_assets.local_path),
                    public_url=COALESCE(NULLIF(excluded.public_url, ''), chapter_assets.public_url),
                    folder=COALESCE(NULLIF(excluded.folder, ''), chapter_assets.folder),
                    content_hash=COALESCE(NULLIF(excluded.content_hash, ''), chapter_assets.content_hash),
                    image_score=COALESCE(excluded.image_score, chapter_assets.image_score),
                    approved=MAX(chapter_assets.approved, excluded.approved),
                    rejected=MAX(chapter_assets.rejected, excluded.rejected),
                    rejection_reason=COALESCE(NULLIF(excluded.rejection_reason, ''), chapter_assets.rejection_reason),
                    provider=COALESCE(NULLIF(excluded.provider, ''), chapter_assets.provider),
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    asset_id,
                    chapter_id or None,
                    abbr or None,
                    asset_type,
                    str(asset.get("platform") or asset.get("platformTarget") or ""),
                    local_path,
                    str(asset.get("publicUrl") or asset.get("url") or ""),
                    folder,
                    str(asset.get("contentHash") or ""),
                    float_or_none(asset.get("imageScore") or asset.get("score")),
                    bool_int(asset.get("approved")),
                    bool_int(asset.get("rejected")),
                    str(asset.get("rejectionReason") or ""),
                    str(asset.get("provider") or ""),
                    dumps_json(asset),
                    now,
                    now,
                ),
            )
            conn.commit()
    return asset_id


def upsert_release_plan_rows(root: Path, rows: list[dict[str, Any]]) -> int:
    init_db(root)
    ensure_default_novels(root)
    now = utc_now_text()
    saved = 0
    with _LOCK:
        with connect(root) as conn:
            for row in rows:
                abbr = normalize_abbr(row.get("novelAbbr") or row.get("abbr") or row.get("novelId"))
                chapter = int_or_none(row.get("chapterNumber") or row.get("chapter"))
                if not abbr or not chapter:
                    continue
                release_plan_id = str(row.get("releasePlanId") or f"{abbr}-{chapter}-{row.get('innerDiscipleDate') or ''}").strip()
                if not release_plan_id:
                    continue
                payload = dict(row)
                payload.setdefault("releasePlanId", release_plan_id)
                payload.setdefault("novelAbbr", abbr)
                payload.setdefault("chapterNumber", chapter)
                conn.execute(
                    """
                    INSERT INTO release_plan_rows(
                        release_plan_id, novel_id, novel_abbr, chapter_number, chapter_title,
                        chapter_source_path, inner_disciple_date, path_initiate_date, royal_road_date,
                        patreon_inner_status, patreon_path_status, royal_road_status,
                        last_prepared_at, last_error, notes, payload_json, created_at, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(novel_abbr, chapter_number) DO UPDATE SET
                        release_plan_id=excluded.release_plan_id,
                        chapter_title=COALESCE(NULLIF(excluded.chapter_title, ''), release_plan_rows.chapter_title),
                        chapter_source_path=COALESCE(NULLIF(excluded.chapter_source_path, ''), release_plan_rows.chapter_source_path),
                        inner_disciple_date=excluded.inner_disciple_date,
                        path_initiate_date=excluded.path_initiate_date,
                        royal_road_date=excluded.royal_road_date,
                        patreon_inner_status=COALESCE(NULLIF(release_plan_rows.patreon_inner_status, ''), excluded.patreon_inner_status),
                        patreon_path_status=COALESCE(NULLIF(release_plan_rows.patreon_path_status, ''), excluded.patreon_path_status),
                        royal_road_status=COALESCE(NULLIF(release_plan_rows.royal_road_status, ''), excluded.royal_road_status),
                        last_prepared_at=COALESCE(NULLIF(release_plan_rows.last_prepared_at, ''), excluded.last_prepared_at),
                        last_error=COALESCE(NULLIF(release_plan_rows.last_error, ''), excluded.last_error),
                        notes=COALESCE(NULLIF(excluded.notes, ''), release_plan_rows.notes),
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        release_plan_id,
                        abbr,
                        abbr,
                        chapter,
                        str(row.get("chapterTitle") or row.get("title") or ""),
                        str(row.get("chapterSourcePath") or ""),
                        str(row.get("innerDiscipleDate") or ""),
                        str(row.get("pathInitiateDate") or ""),
                        str(row.get("royalRoadDate") or ""),
                        str(row.get("patreonInnerStatus") or "planned"),
                        str(row.get("patreonPathStatus") or "planned"),
                        str(row.get("royalRoadStatus") or "planned"),
                        str(row.get("lastPreparedAt") or ""),
                        str(row.get("lastError") or ""),
                        str(row.get("notes") or ""),
                        dumps_json(payload),
                        now,
                        now,
                    ),
                )
                saved += 1
            conn.commit()
    return saved


def load_release_plan_rows(root: Path, abbr: str = "", limit: int = 200) -> list[dict[str, Any]]:
    init_db(root)
    params: list[Any] = []
    where = ""
    abbr = normalize_abbr(abbr)
    if abbr:
        where = "WHERE novel_abbr=?"
        params.append(abbr)
    params.append(max(1, min(int(limit or 200), 1000)))
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM release_plan_rows
                {where}
                ORDER BY inner_disciple_date, novel_abbr, chapter_number
                LIMIT ?
                """,
                params,
            ).fetchall()
    results = []
    for row in rows:
        payload = loads_json(row["payload_json"]) if row["payload_json"] else {}
        if not isinstance(payload, dict):
            payload = {}
        payload.update({
            "releasePlanId": row["release_plan_id"],
            "key": f"{row['novel_abbr']}-{row['chapter_number']}",
            "novelId": row["novel_id"],
            "novelAbbr": row["novel_abbr"],
            "abbr": row["novel_abbr"],
            "chapterNumber": row["chapter_number"],
            "chapter": row["chapter_number"],
            "chapterTitle": row["chapter_title"] or "",
            "title": row["chapter_title"] or "",
            "chapterSourcePath": row["chapter_source_path"] or "",
            "innerDiscipleDate": row["inner_disciple_date"] or "",
            "pathInitiateDate": row["path_initiate_date"] or "",
            "royalRoadDate": row["royal_road_date"] or "",
            "patreonInnerStatus": row["patreon_inner_status"] or "planned",
            "patreonPathStatus": row["patreon_path_status"] or "planned",
            "royalRoadStatus": row["royal_road_status"] or "planned",
            "lastPreparedAt": row["last_prepared_at"] or "",
            "lastError": row["last_error"] or "",
            "notes": row["notes"] or "",
            "updatedAt": row["updated_at"] or "",
        })
        results.append(payload)
    return results


def update_release_plan_row_status(
    root: Path,
    release_plan_id: str,
    *,
    stage: str,
    status: str,
    last_error: str = "",
) -> dict[str, Any]:
    init_db(root)
    stage_key = str(stage or "").strip().lower().replace("-", "_").replace(" ", "_")
    column_by_stage = {
        "inner": "patreon_inner_status",
        "inner_disciple": "patreon_inner_status",
        "patreon_inner": "patreon_inner_status",
        "path": "patreon_path_status",
        "path_initiate": "patreon_path_status",
        "patreon_path": "patreon_path_status",
        "rr": "royal_road_status",
        "royal_road": "royal_road_status",
        "royalroad": "royal_road_status",
    }
    column = column_by_stage.get(stage_key)
    if not column:
        raise ValueError("Choose Inner Disciple, Path Initiate, or Royal Road.")
    normalized_status = str(status or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_status not in {"planned", "draft_prepared", "review_needed", "posted", "skipped_exists", "needs_repair", "blocked"}:
        raise ValueError("Choose a valid release row status.")
    now = utc_now_text()
    with _LOCK:
        with connect(root) as conn:
            found = conn.execute("SELECT payload_json FROM release_plan_rows WHERE release_plan_id=?", (release_plan_id,)).fetchone()
            if not found:
                raise ValueError("Release planner row was not found.")
            payload = loads_json(found["payload_json"]) if found["payload_json"] else {}
            if not isinstance(payload, dict):
                payload = {}
            payload_key = {
                "patreon_inner_status": "patreonInnerStatus",
                "patreon_path_status": "patreonPathStatus",
                "royal_road_status": "royalRoadStatus",
            }[column]
            payload[payload_key] = normalized_status
            payload["lastError"] = last_error
            payload["lastPreparedAt"] = now if normalized_status in {"draft_prepared", "review_needed"} else payload.get("lastPreparedAt", "")
            conn.execute(
                f"""
                UPDATE release_plan_rows
                SET {column}=?, last_error=?, last_prepared_at=CASE
                    WHEN ? IN ('draft_prepared', 'review_needed') THEN ?
                    ELSE last_prepared_at
                END,
                payload_json=?, updated_at=?
                WHERE release_plan_id=?
                """,
                (normalized_status, last_error, normalized_status, now, dumps_json(payload), now, release_plan_id),
            )
            conn.commit()
    rows = [row for row in load_release_plan_rows(root, limit=1000) if row.get("releasePlanId") == release_plan_id]
    return rows[0] if rows else {}


def upsert_platform_post_from_record(root: Path, record: dict[str, Any]) -> str:
    data = normalize_post_record(record)
    automation_id = data["automationRecordId"]
    abbr = normalize_abbr(data.get("novel"))
    if abbr not in DEFAULT_NOVELS:
        abbr = ""
    chapter = int_or_none(data.get("chapter"))
    chapter_id = make_chapter_id(abbr, chapter) if abbr and chapter else ""
    if chapter_id:
        upsert_novel_chapter_from_ledger(root, {"abbr": abbr, "chapter": chapter, "title": data.get("title") or ""})
    elif abbr:
        ensure_default_novels(root)
    platform = str(data.get("platform") or "").strip().lower()
    content_type = str(data.get("contentType") or "post").strip().lower()
    account_id = ensure_platform_account(root, platform, buffer_channel_id=str(data.get("bufferChannelId") or ""))
    asset_id = upsert_chapter_asset(
        root,
        {
            "abbr": abbr,
            "chapter": chapter,
            "title": data.get("title") or "",
            "assetType": infer_asset_type(data),
            "platform": platform,
            "localPath": data.get("localPath") or "",
            "assetFolder": data.get("assetFolder") or "",
            "publicUrl": data.get("mediaUrl") or data.get("publicUrl") or "",
            "provider": data.get("imageProvider") or data.get("provider") or "",
        },
    )
    now = str(data.get("updatedAt") or utc_now_text())
    published_at = str(data.get("publishedAt") or "") if data.get("liveUrl") else ""
    post_id = automation_id
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO platform_posts(
                    post_id, automation_record_id, novel_id, chapter_id, platform_account_id,
                    platform, content_type, campaign_type, caption_status, scheduling_status,
                    publish_date, scheduled_at, published_at, live_url, buffer_post_id,
                    clickup_task_id, asset_folder, primary_asset_id, variant_group_id,
                    variant_label, failure_reason, payload_json, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(automation_record_id) DO UPDATE SET
                    novel_id=COALESCE(excluded.novel_id, platform_posts.novel_id),
                    chapter_id=COALESCE(excluded.chapter_id, platform_posts.chapter_id),
                    platform_account_id=COALESCE(excluded.platform_account_id, platform_posts.platform_account_id),
                    platform=excluded.platform,
                    content_type=excluded.content_type,
                    campaign_type=COALESCE(NULLIF(excluded.campaign_type, ''), platform_posts.campaign_type),
                    caption_status=COALESCE(NULLIF(excluded.caption_status, ''), platform_posts.caption_status),
                    scheduling_status=COALESCE(NULLIF(excluded.scheduling_status, ''), platform_posts.scheduling_status),
                    publish_date=COALESCE(NULLIF(excluded.publish_date, ''), platform_posts.publish_date),
                    scheduled_at=COALESCE(NULLIF(excluded.scheduled_at, ''), platform_posts.scheduled_at),
                    published_at=COALESCE(NULLIF(excluded.published_at, ''), platform_posts.published_at),
                    live_url=COALESCE(NULLIF(excluded.live_url, ''), platform_posts.live_url),
                    buffer_post_id=COALESCE(NULLIF(excluded.buffer_post_id, ''), platform_posts.buffer_post_id),
                    clickup_task_id=COALESCE(NULLIF(excluded.clickup_task_id, ''), platform_posts.clickup_task_id),
                    asset_folder=COALESCE(NULLIF(excluded.asset_folder, ''), platform_posts.asset_folder),
                    primary_asset_id=COALESCE(NULLIF(excluded.primary_asset_id, ''), platform_posts.primary_asset_id),
                    variant_group_id=COALESCE(NULLIF(excluded.variant_group_id, ''), platform_posts.variant_group_id),
                    variant_label=COALESCE(NULLIF(excluded.variant_label, ''), platform_posts.variant_label),
                    failure_reason=COALESCE(NULLIF(excluded.failure_reason, ''), platform_posts.failure_reason),
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    post_id,
                    automation_id,
                    abbr or None,
                    chapter_id or None,
                    account_id or None,
                    platform,
                    content_type,
                    str(data.get("campaignType") or data.get("postType") or ""),
                    str(data.get("captionStatus") or ""),
                    str(data.get("status") or data.get("schedulingStatus") or ""),
                    data["publishDate"],
                    str(data.get("scheduledAt") or ""),
                    published_at,
                    data["liveUrl"],
                    data["bufferPostId"],
                    data["clickupTaskId"],
                    data["assetFolder"],
                    asset_id,
                    str(data.get("variantGroupId") or ""),
                    str(data.get("variantLabel") or ""),
                    str(data.get("failureReason") or data.get("error") or ""),
                    dumps_json(data),
                    str(data.get("createdAt") or now),
                    now,
                ),
            )
            platform_table = ""
            detail_values: tuple[Any, ...] = ()
            detail_sql = ""
            if platform == "youtube":
                platform_table = "youtube_posts"
                detail_sql = """
                    INSERT INTO youtube_posts(
                        post_id, youtube_video_id, youtube_kind, title, description,
                        thumbnail_asset_id, made_for_kids, pinned_comment_status,
                        end_screen_status, playlist_status, upload_status, payload_json, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(post_id) DO UPDATE SET
                        youtube_video_id=COALESCE(NULLIF(excluded.youtube_video_id, ''), youtube_posts.youtube_video_id),
                        youtube_kind=COALESCE(NULLIF(excluded.youtube_kind, ''), youtube_posts.youtube_kind),
                        title=COALESCE(NULLIF(excluded.title, ''), youtube_posts.title),
                        description=COALESCE(NULLIF(excluded.description, ''), youtube_posts.description),
                        thumbnail_asset_id=COALESCE(NULLIF(excluded.thumbnail_asset_id, ''), youtube_posts.thumbnail_asset_id),
                        made_for_kids=excluded.made_for_kids,
                        pinned_comment_status=COALESCE(NULLIF(excluded.pinned_comment_status, ''), youtube_posts.pinned_comment_status),
                        end_screen_status=COALESCE(NULLIF(excluded.end_screen_status, ''), youtube_posts.end_screen_status),
                        playlist_status=COALESCE(NULLIF(excluded.playlist_status, ''), youtube_posts.playlist_status),
                        upload_status=COALESCE(NULLIF(excluded.upload_status, ''), youtube_posts.upload_status),
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                """
                detail_values = (
                    post_id,
                    str(data.get("youtubeVideoId") or data.get("videoId") or ""),
                    "short" if "short" in content_type else "long",
                    data["title"],
                    str(data.get("description") or data.get("caption") or ""),
                    asset_id if "thumbnail" in infer_asset_type(data) else None,
                    bool_int(data.get("madeForKids")),
                    str(data.get("pinnedCommentStatus") or ""),
                    str(data.get("endScreenStatus") or ""),
                    str(data.get("playlistStatus") or ""),
                    str(data.get("uploadStatus") or data.get("status") or ""),
                    dumps_json(data),
                    now,
                )
            elif platform == "tiktok":
                platform_table = "tiktok_posts"
                detail_sql = """
                    INSERT INTO tiktok_posts(post_id, video_asset_id, sound_asset_id, duration_seconds, overlay_status, deep_tiktok, payload_json, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(post_id) DO UPDATE SET
                        video_asset_id=COALESCE(NULLIF(excluded.video_asset_id, ''), tiktok_posts.video_asset_id),
                        sound_asset_id=COALESCE(NULLIF(excluded.sound_asset_id, ''), tiktok_posts.sound_asset_id),
                        duration_seconds=COALESCE(excluded.duration_seconds, tiktok_posts.duration_seconds),
                        overlay_status=COALESCE(NULLIF(excluded.overlay_status, ''), tiktok_posts.overlay_status),
                        deep_tiktok=MAX(tiktok_posts.deep_tiktok, excluded.deep_tiktok),
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                """
                detail_values = (post_id, asset_id or None, None, float_or_none(data.get("durationSeconds")), str(data.get("overlayStatus") or ""), bool_int(data.get("deepTikTok") or ("deep" in content_type)), dumps_json(data), now)
            elif platform == "instagram":
                platform_table = "instagram_posts"
                detail_sql = """
                    INSERT INTO instagram_posts(post_id, instagram_kind, image_asset_id, video_asset_id, payload_json, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(post_id) DO UPDATE SET
                        instagram_kind=COALESCE(NULLIF(excluded.instagram_kind, ''), instagram_posts.instagram_kind),
                        image_asset_id=COALESCE(NULLIF(excluded.image_asset_id, ''), instagram_posts.image_asset_id),
                        video_asset_id=COALESCE(NULLIF(excluded.video_asset_id, ''), instagram_posts.video_asset_id),
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                """
                is_video = infer_asset_type(data) in {"short_video", "youtube_video", "short_pack"}
                detail_values = (post_id, "reel" if "reel" in content_type else "post", None if is_video else (asset_id or None), asset_id if is_video else None, dumps_json(data), now)
            elif platform == "facebook":
                platform_table = "facebook_posts"
                detail_sql = """
                    INSERT INTO facebook_posts(post_id, facebook_kind, browser_draft_status, payload_json, updated_at)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(post_id) DO UPDATE SET
                        facebook_kind=COALESCE(NULLIF(excluded.facebook_kind, ''), facebook_posts.facebook_kind),
                        browser_draft_status=COALESCE(NULLIF(excluded.browser_draft_status, ''), facebook_posts.browser_draft_status),
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                """
                detail_values = (post_id, str(data.get("facebookKind") or content_type), str(data.get("browserDraftStatus") or data.get("status") or ""), dumps_json(data), now)
            elif platform == "x":
                platform_table = "x_posts"
                detail_sql = """
                    INSERT INTO x_posts(post_id, character_count, browser_draft_status, payload_json, updated_at)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(post_id) DO UPDATE SET
                        character_count=COALESCE(excluded.character_count, x_posts.character_count),
                        browser_draft_status=COALESCE(NULLIF(excluded.browser_draft_status, ''), x_posts.browser_draft_status),
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                """
                detail_values = (post_id, int_or_none(data.get("characterCount")) or len(str(data.get("caption") or data.get("text") or "")), str(data.get("browserDraftStatus") or data.get("status") or ""), dumps_json(data), now)
            elif platform == "patreon":
                platform_table = "patreon_posts"
                detail_sql = """
                    INSERT INTO patreon_posts(post_id, tier, scheduled_for, draft_url, browser_draft_status, payload_json, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(post_id) DO UPDATE SET
                        tier=COALESCE(NULLIF(excluded.tier, ''), patreon_posts.tier),
                        scheduled_for=COALESCE(NULLIF(excluded.scheduled_for, ''), patreon_posts.scheduled_for),
                        draft_url=COALESCE(NULLIF(excluded.draft_url, ''), patreon_posts.draft_url),
                        browser_draft_status=COALESCE(NULLIF(excluded.browser_draft_status, ''), patreon_posts.browser_draft_status),
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                """
                detail_values = (post_id, str(data.get("tier") or ""), str(data.get("scheduledFor") or data.get("publishDate") or ""), str(data.get("draftUrl") or ""), str(data.get("browserDraftStatus") or data.get("status") or ""), dumps_json(data), now)
            elif platform in {"royalroad", "royal_road"}:
                platform_table = "royal_road_posts"
                detail_sql = """
                    INSERT INTO royal_road_posts(post_id, chapter_id, edit_url, diff_status, author_note_status, browser_draft_status, payload_json, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(post_id) DO UPDATE SET
                        chapter_id=COALESCE(excluded.chapter_id, royal_road_posts.chapter_id),
                        edit_url=COALESCE(NULLIF(excluded.edit_url, ''), royal_road_posts.edit_url),
                        diff_status=COALESCE(NULLIF(excluded.diff_status, ''), royal_road_posts.diff_status),
                        author_note_status=COALESCE(NULLIF(excluded.author_note_status, ''), royal_road_posts.author_note_status),
                        browser_draft_status=COALESCE(NULLIF(excluded.browser_draft_status, ''), royal_road_posts.browser_draft_status),
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                """
                detail_values = (post_id, chapter_id or None, str(data.get("editUrl") or ""), str(data.get("diffStatus") or ""), str(data.get("authorNoteStatus") or ""), str(data.get("browserDraftStatus") or data.get("status") or ""), dumps_json(data), now)
            if platform_table and detail_sql:
                conn.execute(detail_sql, detail_values)
            conn.commit()
    return post_id


def normalize_post_record(record: dict[str, Any]) -> dict[str, Any]:
    data = dict(record)
    if PostRecordModel:
        data = PostRecordModel.model_validate(data).model_dump(mode="json")
    data["automationRecordId"] = str(data.get("automationRecordId") or "").strip()
    if not data["automationRecordId"]:
        raise ValueError("Post record needs automationRecordId.")
    for key in [
        "clickupTaskId",
        "novel",
        "chapter",
        "platform",
        "contentType",
        "publishDate",
        "liveUrl",
        "bufferPostId",
        "assetFolder",
        "localPath",
        "title",
        "status",
    ]:
        data[key] = str(data.get(key) or "")
    return data


def upsert_post_record(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    data = normalize_post_record(record)
    now = utc_now_text()
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO post_records(
                    automation_record_id, clickup_task_id, novel, chapter, platform, content_type,
                    publish_date, live_url, buffer_post_id, asset_folder, local_path, title, status,
                    payload_json, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(automation_record_id) DO UPDATE SET
                    clickup_task_id=excluded.clickup_task_id,
                    novel=excluded.novel,
                    chapter=excluded.chapter,
                    platform=excluded.platform,
                    content_type=excluded.content_type,
                    publish_date=excluded.publish_date,
                    live_url=excluded.live_url,
                    buffer_post_id=excluded.buffer_post_id,
                    asset_folder=excluded.asset_folder,
                    local_path=excluded.local_path,
                    title=excluded.title,
                    status=excluded.status,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    data["automationRecordId"],
                    data["clickupTaskId"],
                    data["novel"],
                    data["chapter"],
                    data["platform"],
                    data["contentType"],
                    data["publishDate"],
                    data["liveUrl"],
                    data["bufferPostId"],
                    data["assetFolder"],
                    data["localPath"],
                    data["title"],
                    data["status"],
                    dumps_json(data),
                    str(data.get("createdAt") or now),
                    now,
                ),
            )
            conn.commit()
    try:
        upsert_platform_post_from_record(root, data)
    except Exception:
        pass
    return data


def load_post_records(root: Path) -> dict[str, Any]:
    path = init_db(root)
    if not path.exists():
        return {"schemaVersion": 1, "records": {}}
    records: dict[str, Any] = {}
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute("SELECT automation_record_id, payload_json FROM post_records").fetchall()
    for row in rows:
        try:
            payload = loads_json(row["payload_json"])
        except Exception:
            payload = None
        if isinstance(payload, dict):
            records[str(row["automation_record_id"])] = payload
    return {"schemaVersion": 1, "records": records, "source": "sqlite"}


def find_post_records(
    root: Path,
    *,
    novel: str = "",
    chapter: str | int = "",
    platform: str = "",
    content_type: str = "",
    asset_folder: str = "",
) -> list[dict[str, Any]]:
    init_db(root)
    clauses: list[str] = []
    params: list[Any] = []
    if novel:
        clauses.append("lower(novel)=lower(?)")
        params.append(str(novel))
    if str(chapter).strip():
        clauses.append("chapter=?")
        params.append(str(chapter))
    if platform:
        clauses.append("lower(platform)=lower(?)")
        params.append(str(platform))
    if content_type:
        clauses.append("lower(content_type)=lower(?)")
        params.append(str(content_type))
    if asset_folder:
        clauses.append("lower(asset_folder)=lower(?)")
        params.append(str(asset_folder))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute(
                f"SELECT payload_json FROM post_records{where} ORDER BY updated_at DESC",
                params,
            ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = loads_json(row["payload_json"])
        except Exception:
            payload = None
        if isinstance(payload, dict):
            result.append(payload)
    return result


def upsert_chapter_ledger_entry(root: Path, entry: dict[str, Any]) -> None:
    abbr = str(entry.get("abbr") or "").strip().upper()
    chapter = int(entry.get("chapter") or 0)
    if not abbr or chapter <= 0:
        return
    key = f"{abbr}-{chapter}"
    now = str(entry.get("updatedAt") or utc_now_text())
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO chapter_ledger(ledger_key, abbr, chapter, novel, title, payload_json, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ledger_key) DO UPDATE SET
                    abbr=excluded.abbr,
                    chapter=excluded.chapter,
                    novel=excluded.novel,
                    title=excluded.title,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    key,
                    abbr,
                    chapter,
                    str(entry.get("novel") or ""),
                    str(entry.get("title") or ""),
                    dumps_json(entry),
                    now,
                ),
            )
            conn.commit()
    try:
        upsert_novel_chapter_from_ledger(root, entry)
    except Exception:
        pass


def upsert_release_status(root: Path, status: dict[str, Any]) -> None:
    init_db(root)
    now = utc_now_text()
    chapters = status.get("chapters") if isinstance(status.get("chapters"), dict) else {}
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO release_status(status_key, abbr, chapter, payload_json, updated_at)
                VALUES('GLOBAL', '', NULL, ?, ?)
                ON CONFLICT(status_key) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (dumps_json(status), now),
            )
            for key, entry in chapters.items():
                if not isinstance(entry, dict):
                    continue
                abbr = str(entry.get("abbr") or str(key).split("-")[0]).strip().upper()
                try:
                    chapter = int(entry.get("chapter") or str(key).split("-")[-1])
                except (TypeError, ValueError):
                    chapter = 0
                conn.execute(
                    """
                    INSERT INTO release_status(status_key, abbr, chapter, payload_json, updated_at)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(status_key) DO UPDATE SET
                        abbr=excluded.abbr,
                        chapter=excluded.chapter,
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                    """,
                    (str(key), abbr, chapter if chapter > 0 else None, dumps_json(entry), now),
                )
            conn.commit()


def load_release_status(root: Path) -> dict[str, Any] | None:
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            row = conn.execute("SELECT payload_json FROM release_status WHERE status_key='GLOBAL'").fetchone()
    if not row:
        return None
    try:
        payload = loads_json(row["payload_json"])
    except Exception:
        payload = None
    if isinstance(payload, dict):
        payload.setdefault("chapters", {})
        payload["_source"] = "sqlite"
        return payload
    return None


def load_release_status_entry(root: Path, abbr: str, chapter: int | str) -> dict[str, Any] | None:
    abbr = str(abbr or "").strip().upper()
    try:
        chapter_number = int(chapter)
    except (TypeError, ValueError):
        return None
    if not abbr or chapter_number <= 0:
        return None
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            row = conn.execute(
                "SELECT payload_json FROM release_status WHERE status_key=? OR (abbr=? AND chapter=?) ORDER BY status_key=? DESC LIMIT 1",
                (f"{abbr}-{chapter_number}", abbr, chapter_number, f"{abbr}-{chapter_number}"),
            ).fetchone()
    if not row:
        return None
    try:
        payload = loads_json(row["payload_json"])
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def upsert_approval_cleared(root: Path, approval_key: str, record: dict[str, Any]) -> None:
    if not approval_key:
        return
    now = utc_now_text()
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO approval_cleared(
                    approval_key, kind, abbr, chapter, platform, folder, comment_id, reason,
                    payload_json, cleared_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(approval_key) DO UPDATE SET
                    kind=excluded.kind,
                    abbr=excluded.abbr,
                    chapter=excluded.chapter,
                    platform=excluded.platform,
                    folder=excluded.folder,
                    comment_id=excluded.comment_id,
                    reason=excluded.reason,
                    payload_json=excluded.payload_json,
                    cleared_at=excluded.cleared_at,
                    updated_at=excluded.updated_at
                """,
                (
                    approval_key,
                    str(record.get("kind") or ""),
                    str(record.get("abbr") or ""),
                    str(record.get("chapter") or ""),
                    str(record.get("platform") or ""),
                    str(record.get("folder") or ""),
                    str(record.get("commentId") or ""),
                    str(record.get("reason") or ""),
                    dumps_json(record),
                    str(record.get("clearedAt") or now),
                    now,
                ),
            )
            conn.commit()


def insert_recovery_event(root: Path, event: dict[str, Any]) -> None:
    init_db(root)
    payload = dumps_json(event)
    event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO recovery_events(
                    event_hash, step, error_type, abbr, chapter, folder, reason, retry_path, payload_json, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_hash) DO NOTHING
                """,
                (
                    event_hash,
                    str(event.get("step") or ""),
                    str(event.get("errorType") or ""),
                    str(event.get("abbr") or ""),
                    str(event.get("chapter") or ""),
                    str(event.get("folder") or ""),
                    str(event.get("reason") or ""),
                    str(event.get("retryPath") or ""),
                    payload,
                    str(event.get("time") or utc_now_text()),
                ),
            )
            conn.commit()


def insert_agent_post_run(
    root: Path,
    *,
    run_id: str,
    novel: str,
    chapter: str,
    title: str,
    status: str,
    fallback_reason: str | None = None,
    hermes_profile: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    command_flags: str | None = None,
    request_text: str | None = None,
    decoded_stdout: str | None = None,
    raw_stdout: bytes | None = None,
    stderr_text: str | None = None,
    selected_final_block: str | None = None,
    hook: str | None = None,
    caption: str | None = None,
    cta: str | None = None,
    content_angle: str | None = None,
    intended_audience: str | None = None,
    parse_mode: str | None = None,
    validation_errors: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    duration_ms: int | None = None,
    exit_code: int | None = None,
) -> None:
    """Persist one agent-post attempt (success OR failure) as the lifecycle source of truth.

    Failed runs are the most valuable diagnostic records, so they are stored too.
    The application owns this transaction; Hermes never writes here.
    """
    init_db(root)
    now = utc_now_text()
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO agent_post_runs(
                    run_id, novel, chapter, title, status, fallback_reason, hermes_profile,
                    provider, model, command_flags, request_text, decoded_stdout, raw_stdout,
                    stderr_text, selected_final_block, hook, caption, cta, content_angle,
                    intended_audience, schema_version, parse_mode, validation_errors,
                    started_at, completed_at, duration_ms, exit_code, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    fallback_reason=excluded.fallback_reason,
                    decoded_stdout=excluded.decoded_stdout,
                    raw_stdout=excluded.raw_stdout,
                    stderr_text=excluded.stderr_text,
                    selected_final_block=excluded.selected_final_block,
                    hook=excluded.hook,
                    caption=excluded.caption,
                    cta=excluded.cta,
                    content_angle=excluded.content_angle,
                    intended_audience=excluded.intended_audience,
                    parse_mode=excluded.parse_mode,
                    validation_errors=excluded.validation_errors,
                    completed_at=excluded.completed_at,
                    duration_ms=excluded.duration_ms,
                    exit_code=excluded.exit_code,
                    created_at=excluded.created_at
                """,
                (
                    str(run_id), str(novel or ""), str(chapter or ""), str(title or ""),
                    str(status), str(fallback_reason or "") or None,
                    str(hermes_profile or "") or None, str(provider or "") or None, str(model or "") or None,
                    str(command_flags or "") or None, str(request_text or "") or None,
                    str(decoded_stdout or "") or None, raw_stdout, str(stderr_text or "") or None,
                    str(selected_final_block or "") or None, str(hook or "") or None,
                    str(caption or "") or None, str(cta or "") or None,
                    str(content_angle or "") or None, str(intended_audience or "") or None,
                    "social-post-v1", str(parse_mode or "") or None, str(validation_errors or "") or None,
                    str(started_at or "") or None, str(completed_at or "") or None,
                    int(duration_ms) if duration_ms is not None else None,
                    int(exit_code) if exit_code is not None else None, now,
                ),
            )
            conn.commit()


def replace_agent_post_fields(root: Path, run_id: str, fields: list[tuple[int, str, str | None]]) -> None:
    """Replace the per-field record for a run (position, field, value)."""
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            conn.execute("DELETE FROM agent_post_fields WHERE run_id=?", (str(run_id),))
            for position, field, value in fields:
                conn.execute(
                    """
                    INSERT INTO agent_post_fields(run_id, position, field, value)
                    VALUES(?, ?, ?, ?)
                    """,
                    (str(run_id), int(position), str(field), None if value is None else str(value)),
                )
            conn.commit()


def insert_generated_social_posts(
    root: Path, run_id: str, posts: list[tuple[str, str, bool, str | None]]
) -> None:
    """Record each generated platform post for a run (platform, text, agent_used, fallback_reason)."""
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            for platform, post_text, agent_used, fallback_reason in posts:
                conn.execute(
                    """
                    INSERT INTO generated_social_posts(run_id, platform, post_text, agent_used, fallback_reason)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, platform) DO UPDATE SET
                        post_text=excluded.post_text,
                        agent_used=excluded.agent_used,
                        fallback_reason=excluded.fallback_reason
                    """,
                    (str(run_id), str(platform), str(post_text or ""), 1 if agent_used else 0, str(fallback_reason or "") or None),
                )
            conn.commit()


def upsert_state_snapshot(root: Path, key: str, payload: dict[str, Any]) -> None:
    key = str(key or "").strip()
    if not key:
        return
    init_db(root)
    now = utc_now_text()
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO state_snapshots(state_key, payload_json, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (key, dumps_json(payload), now),
            )
            conn.commit()


def load_state_snapshot(root: Path, key: str) -> dict[str, Any] | None:
    key = str(key or "").strip()
    if not key:
        return None
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            row = conn.execute(
                "SELECT payload_json FROM state_snapshots WHERE state_key=? LIMIT 1",
                (key,),
            ).fetchone()
    if not row:
        return None
    try:
        payload = loads_json(row["payload_json"])
    except Exception:
        payload = None
    if isinstance(payload, dict):
        payload["_source"] = "sqlite"
        return payload
    return None


def save_social_stats_daily(
    root: Path,
    platform: str,
    channel: str,
    collected_date: str,
    metrics: dict[str, Any],
) -> None:
    init_db(root)
    now = utc_now_text()
    stat_id = stable_id("social", platform, channel, collected_date)
    with _LOCK:
        with connect(root) as conn:
            conn.execute(
                """
                INSERT INTO social_stats_daily(
                    stat_id, platform, channel, collected_date, metrics_json, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(stat_id) DO UPDATE SET
                    metrics_json=excluded.metrics_json,
                    created_at=excluded.created_at
                """,
                (stat_id, platform, channel, collected_date, dumps_json(metrics), now),
            )
            conn.commit()


def record_social_stats_from_gather(
    root: Path,
    normalized_results: list[dict[str, Any]],
    raw_payload: Any = None,
) -> int:
    """SC-6: normalize metrics-gather output into social_stats_daily.

    One upsert per (platform, channel, collected_date), keyed identically to
    save_social_stats_daily (same stat_id). Stores a raw-source provenance hash
    (sha256 over the normalized payload) so a row can be traced back to the
    exact gather run that produced it. Idempotent: re-running with the same
    payload overwrites in place.
    """
    if not normalized_results:
        return 0
    raw_hash = None
    if raw_payload is not None:
        try:
            raw_hash = hashlib.sha256(
                json.dumps(raw_payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
        except Exception:
            raw_hash = None
    now = utc_now_text()
    written = 0
    with _LOCK:
        with connect(root) as conn:
            # Ensure the SC-6 provenance column exists even if migration 004
            # has not been applied yet (defensive; migration is idempotent).
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(social_stats_daily)").fetchall()}
            if "raw_source_hash" not in cols:
                conn.execute("ALTER TABLE social_stats_daily ADD COLUMN raw_source_hash TEXT")
            for item in normalized_results:
                platform = str(item.get("platform") or "unknown").lower()
                channel = str(item.get("channel") or item.get("url") or platform)
                collected_date = str(item.get("collected_date") or item.get("gatheredAt") or now)[:10]
                stat_id = stable_id("social", platform, channel, collected_date)
                metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
                conn.execute(
                    """
                    INSERT INTO social_stats_daily(
                        stat_id, platform, channel, collected_date, metrics_json, created_at, raw_source_hash
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(stat_id) DO UPDATE SET
                        metrics_json=excluded.metrics_json,
                        created_at=excluded.created_at,
                        raw_source_hash=excluded.raw_source_hash
                    """,
                    (stat_id, platform, channel, collected_date, dumps_json(metrics), now, raw_hash),
                )
                written += 1
            conn.commit()
    return written



def load_social_stats_daily(root: Path, collected_date: str) -> list[dict[str, Any]]:
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute(
                "SELECT platform, channel, metrics_json FROM social_stats_daily "
                "WHERE collected_date=? ORDER BY platform, channel",
                (collected_date,),
            ).fetchall()
    out = []
    for row in rows:
        try:
            metrics = loads_json(row["metrics_json"])
        except Exception:
            metrics = {}
        out.append({"platform": row["platform"], "channel": row["channel"], "metrics": metrics})
    return out


def load_social_stats_recent(root: Path, limit: int = 30) -> list[dict[str, Any]]:
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute(
                "SELECT platform, channel, collected_date, metrics_json "
                "FROM social_stats_daily ORDER BY collected_date DESC, platform, channel LIMIT ?",
                (int(limit),),
            ).fetchall()
    out = []
    for row in rows:
        try:
            metrics = loads_json(row["metrics_json"])
        except Exception:
            metrics = {}
        out.append(
            {
                "platform": row["platform"],
                "channel": row["channel"],
                "collected_date": row["collected_date"],
                "metrics": metrics,
            }
        )
    return out


def load_chapter_ledger(root: Path) -> dict[str, Any]:
    init_db(root)
    chapters: dict[str, Any] = {}
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute("SELECT ledger_key, payload_json FROM chapter_ledger").fetchall()
    for row in rows:
        try:
            payload = loads_json(row["payload_json"])
        except Exception:
            payload = None
        if isinstance(payload, dict):
            chapters[str(row["ledger_key"])] = payload
    return {"schemaVersion": 1, "chapters": chapters, "source": "sqlite"}


def load_chapter_ledger_entry(root: Path, abbr: str, chapter: int | str) -> dict[str, Any] | None:
    abbr = str(abbr or "").strip().upper()
    try:
        chapter_number = int(chapter)
    except (TypeError, ValueError):
        return None
    if not abbr or chapter_number <= 0:
        return None
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            row = conn.execute(
                "SELECT payload_json FROM chapter_ledger WHERE ledger_key=? OR (abbr=? AND chapter=?) LIMIT 1",
                (f"{abbr}-{chapter_number}", abbr, chapter_number),
            ).fetchone()
    if not row:
        return None
    try:
        payload = loads_json(row["payload_json"])
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def is_approval_cleared(root: Path, approval_key: str) -> bool:
    if not approval_key:
        return False
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            row = conn.execute(
                "SELECT 1 FROM approval_cleared WHERE approval_key=? LIMIT 1",
                (approval_key,),
            ).fetchone()
    return bool(row)


def load_approval_cleared_state(root: Path) -> dict[str, Any]:
    init_db(root)
    items: dict[str, Any] = {}
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute("SELECT approval_key, payload_json FROM approval_cleared").fetchall()
    for row in rows:
        try:
            payload = loads_json(row["payload_json"])
        except Exception:
            payload = None
        if isinstance(payload, dict):
            items[str(row["approval_key"])] = payload
    return {"schemaVersion": 1, "items": items, "source": "sqlite"}


def duplicate_asset_folders(root: Path, abbr: str, chapter: int | str, exclude_folder: str = "") -> list[str]:
    abbr = str(abbr or "").strip().upper()
    chapter_text = str(chapter or "").strip()
    if not abbr or not chapter_text:
        return []
    folders: set[str] = set()
    exclude = str(Path(exclude_folder).resolve()).lower() if exclude_folder else ""
    for record in find_post_records(root, novel=abbr, chapter=chapter_text):
        folder = str(record.get("assetFolder") or record.get("localPath") or "").strip()
        if not folder:
            continue
        try:
            resolved = str(Path(folder).resolve())
        except Exception:
            resolved = folder
        if exclude and resolved.lower() == exclude:
            continue
        folders.add(resolved)
    entry = load_chapter_ledger_entry(root, abbr, chapter_text)
    if isinstance(entry, dict):
        for folder in (entry.get("folders") or {}).values():
            folder_text = str(folder or "").strip()
            if not folder_text:
                continue
            try:
                resolved = str(Path(folder_text).resolve())
            except Exception:
                resolved = folder_text
            if exclude and resolved.lower() == exclude:
                continue
            folders.add(resolved)
    return sorted(folders)


def recent_duplicate_post_groups(root: Path, days: int = 30) -> list[dict[str, Any]]:
    init_db(root)
    cutoff_epoch = time.time() - max(1, int(days or 30)) * 86400
    cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(cutoff_epoch))
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute(
                """
                SELECT novel, chapter, content_type, COUNT(DISTINCT asset_folder) AS count
                FROM post_records
                WHERE updated_at >= ?
                  AND novel != ''
                  AND chapter != ''
                  AND lower(chapter) != 'general'
                  AND asset_folder != ''
                  AND lower(asset_folder) NOT LIKE '%experiment-post-packs%'
                  AND lower(content_type) NOT LIKE 'experiment%'
                  AND lower(content_type) != 'variant-test'
                GROUP BY lower(novel), chapter, lower(content_type)
                HAVING COUNT(DISTINCT asset_folder) > 1
                ORDER BY count DESC
                LIMIT 30
                """,
                (cutoff,),
            ).fetchall()
    warnings: list[dict[str, Any]] = []
    for row in rows:
        records = find_post_records(
            root,
            novel=str(row["novel"]),
            chapter=str(row["chapter"]),
            content_type=str(row["content_type"] or ""),
        )
        folders = []
        for record in records:
            folder = str(record.get("assetFolder") or record.get("localPath") or "").strip()
            if folder and folder not in folders:
                folders.append(folder)
        warnings.append(
            {
                "key": f"{row['novel']}:{row['chapter']}:{row['content_type']}",
                "count": int(row["count"]),
                "abbr": str(row["novel"]),
                "chapter": str(row["chapter"]),
                "contentType": str(row["content_type"] or ""),
                "folders": folders[:8],
                "source": "sqlite",
                "recommendation": "Reuse or rebuild the newest valid pack instead of creating another duplicate folder.",
            }
        )
    return warnings


def backfill_normalized_tables(root: Path) -> dict[str, Any]:
    init_db(root)
    ensure_default_novels(root)
    imported: dict[str, Any] = {"novels": len(DEFAULT_NOVELS), "chapters": 0, "posts": 0, "assets": 0, "errors": []}
    with _LOCK:
        with connect(root) as conn:
            ledger_rows = conn.execute("SELECT payload_json FROM chapter_ledger").fetchall()
            post_rows = conn.execute("SELECT payload_json FROM post_records").fetchall()
    for row in ledger_rows:
        try:
            payload = loads_json(row["payload_json"])
            if isinstance(payload, dict) and upsert_novel_chapter_from_ledger(root, payload):
                imported["chapters"] += 1
        except Exception as exc:
            imported["errors"].append(f"chapter: {exc}")
    for row in post_rows:
        try:
            payload = loads_json(row["payload_json"])
            if isinstance(payload, dict):
                post_id = upsert_platform_post_from_record(root, payload)
                if post_id:
                    imported["posts"] += 1
                    if payload.get("assetFolder") or payload.get("localPath"):
                        imported["assets"] += 1
        except Exception as exc:
            imported["errors"].append(f"post: {exc}")
    imported["errors"] = imported["errors"][:25]
    return imported


def normalized_database_summary(root: Path) -> dict[str, Any]:
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            chapter_rows = conn.execute(
                """
                SELECT novel_id, COUNT(*) AS chapters, MAX(chapter_number) AS max_chapter
                FROM novel_chapters
                GROUP BY novel_id
                ORDER BY novel_id
                """
            ).fetchall()
            platform_rows = conn.execute(
                """
                SELECT platform, content_type, scheduling_status, COUNT(*) AS count
                FROM platform_posts
                GROUP BY platform, content_type, scheduling_status
                ORDER BY platform, content_type, scheduling_status
                """
            ).fetchall()
            next_rows = conn.execute(
                """
                SELECT n.abbr, n.title,
                       MIN(CASE WHEN COALESCE(c.royal_road_exists, 0)=0 THEN c.chapter_number END) AS next_missing_royal_road,
                       MIN(CASE WHEN COALESCE(c.patreon_inner_exists, 0)=0 THEN c.chapter_number END) AS next_missing_inner,
                       MIN(CASE WHEN COALESCE(c.patreon_path_exists, 0)=0 THEN c.chapter_number END) AS next_missing_path
                FROM novels n
                LEFT JOIN novel_chapters c ON c.novel_id=n.novel_id
                GROUP BY n.abbr, n.title
                ORDER BY n.abbr
                """
            ).fetchall()
    return {
        "chaptersByNovel": [
            {
                "novel": str(row["novel_id"]),
                "chapters": int(row["chapters"] or 0),
                "maxChapter": int(row["max_chapter"] or 0),
            }
            for row in chapter_rows
        ],
        "postsByPlatform": [
            {
                "platform": str(row["platform"] or ""),
                "contentType": str(row["content_type"] or ""),
                "status": str(row["scheduling_status"] or ""),
                "count": int(row["count"] or 0),
            }
            for row in platform_rows
        ],
        "nextMissing": [
            {
                "novel": str(row["abbr"] or ""),
                "title": str(row["title"] or ""),
                "royalRoad": int(row["next_missing_royal_road"]) if row["next_missing_royal_road"] is not None else None,
                "innerDisciple": int(row["next_missing_inner"]) if row["next_missing_inner"] is not None else None,
                "pathInitiate": int(row["next_missing_path"]) if row["next_missing_path"] is not None else None,
            }
            for row in next_rows
        ],
    }


def database_status(root: Path) -> dict[str, Any]:
    path = init_db(root)
    ensure_default_novels(root)
    tables = [
        "post_records",
        "chapter_ledger",
        "release_status",
        "approval_cleared",
        "recovery_events",
        "state_snapshots",
        "novels",
        "novel_chapters",
        "chapter_assets",
        "platform_accounts",
        "platform_posts",
        "youtube_posts",
        "tiktok_posts",
        "instagram_posts",
        "facebook_posts",
        "x_posts",
        "patreon_posts",
        "royal_road_posts",
        "release_plan_rows",
        "release_automation_jobs",
        "platform_post_metrics",
        "platform_post_actions",
        "weekly_growth_plans",
        "weekly_growth_slots",
    ]
    counts: dict[str, int] = {}
    with _LOCK:
        with connect(root) as conn:
            for table in tables:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            schema = conn.execute("SELECT value FROM app_meta WHERE key='schemaVersion'").fetchone()
    return {
        "ok": True,
        "path": str(path),
        "exists": path.exists(),
        "schemaVersion": int(schema["value"]) if schema else SCHEMA_VERSION,
        "counts": counts,
        "normalized": normalized_database_summary(root),
        "message": "SQLite state database is ready.",
    }


def bootstrap_from_json_files(root: Path, files: dict[str, Path]) -> dict[str, Any]:
    init_db(root)
    imported = {"postRecords": 0, "chapterLedger": 0, "releaseStatus": 0, "approvalCleared": 0, "recoveryEvents": 0, "stateSnapshots": 0}

    def read_json(path: Path) -> Any:
        # Guard against empty/falsy paths (Path("") normalizes to ".") which
        # would resolve to cwd and either read the wrong file or raise on
        # permission. A missing key in the file map yields Path("") -> skip.
        norm = str(path).strip().rstrip("/\\")
        if not norm or norm in (".", ".."):
            return None
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8-sig"))

    post_records = read_json(files.get("postRecords", Path("")))
    if isinstance(post_records, dict):
        for record in (post_records.get("records") or {}).values():
            if isinstance(record, dict):
                upsert_post_record(root, record)
                imported["postRecords"] += 1

    chapter_ledger = read_json(files.get("chapterLedger", Path("")))
    if isinstance(chapter_ledger, dict):
        for entry in (chapter_ledger.get("chapters") or {}).values():
            if isinstance(entry, dict):
                upsert_chapter_ledger_entry(root, entry)
                imported["chapterLedger"] += 1

    release_status = read_json(files.get("releaseStatus", Path("")))
    if isinstance(release_status, dict):
        upsert_release_status(root, release_status)
        imported["releaseStatus"] += len(release_status.get("chapters") or {}) + 1

    approval_state = read_json(files.get("approvalCleared", Path("")))
    if isinstance(approval_state, dict):
        for key, record in (approval_state.get("items") or {}).items():
            if isinstance(record, dict):
                upsert_approval_cleared(root, str(key), record)
                imported["approvalCleared"] += 1

    recovery = read_json(files.get("recoveryLog", Path("")))
    if isinstance(recovery, dict):
        for event in recovery.get("events") or []:
            if isinstance(event, dict):
                insert_recovery_event(root, event)
                imported["recoveryEvents"] += 1

    for key in ["chapterPath", "chapterReleaseQueue"]:
        payload = read_json(files.get(key, Path("")))
        if isinstance(payload, dict):
            upsert_state_snapshot(root, key, payload)
            imported["stateSnapshots"] += 1

    normalized = backfill_normalized_tables(root)
    status = database_status(root)
    return {"ok": True, "imported": imported, "normalized": normalized, "database": status}


def save_weekly_growth_plan(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    init_db(root)
    plan_id = str(plan.get("planId") or "").strip()
    week_start = str(plan.get("weekStart") or "").strip()
    week_end = str(plan.get("weekEnd") or "").strip()
    if not plan_id or not week_start or not week_end:
        raise ValueError("Weekly growth plan requires planId, weekStart, and weekEnd.")
    now = utc_now_text()
    slots = [item for item in (plan.get("slots") or []) if isinstance(item, dict)]
    with _LOCK:
        with connect(root) as conn:
            existing = conn.execute("SELECT created_at FROM weekly_growth_plans WHERE plan_id=?", (plan_id,)).fetchone()
            created_at = str(existing["created_at"] if existing else now)
            conn.execute(
                """
                INSERT INTO weekly_growth_plans(
                    plan_id, week_start, week_end, status, weights_json, summary_json,
                    payload_json, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    week_start=excluded.week_start,
                    week_end=excluded.week_end,
                    status=excluded.status,
                    weights_json=excluded.weights_json,
                    summary_json=excluded.summary_json,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    plan_id, week_start, week_end, str(plan.get("status") or "draft"),
                    dumps_json(plan.get("weights") or {}), dumps_json(plan.get("summary") or {}),
                    dumps_json(plan), created_at, now,
                ),
            )
            conn.execute("DELETE FROM weekly_growth_slots WHERE plan_id=?", (plan_id,))
            for item in slots:
                number = int(item.get("slot") or 0)
                if number <= 0:
                    continue
                score_data = item.get("predictedEngagement") if isinstance(item.get("predictedEngagement"), dict) else {}
                diversity = score_data.get("diversity") if isinstance(score_data.get("diversity"), dict) else {}
                slot_id = stable_id(plan_id, number)
                conn.execute(
                    """
                    INSERT INTO weekly_growth_slots(
                        slot_id, plan_id, slot_number, slot_date, day_name, slot_type,
                        novel_abbr, chapter_number, engagement_goal, predicted_score,
                        quality_status, delivery_status, hook_fingerprint, cta_fingerprint,
                        image_fingerprint, payload_json, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        slot_id, plan_id, number, str(item.get("date") or ""), str(item.get("day") or ""),
                        str(item.get("type") or "novel"), str(item.get("abbr") or ""), int_or_none(item.get("chapter")),
                        str(item.get("engagementGoal") or ""), float(score_data.get("score") or 0),
                        str(score_data.get("classification") or "weak"), str(item.get("deliveryStatus") or "ready"),
                        hashlib.sha256(str(item.get("hook") or "").strip().lower().encode("utf-8")).hexdigest()[:24],
                        hashlib.sha256(str(item.get("cta") or "").strip().lower().encode("utf-8")).hexdigest()[:24],
                        hashlib.sha256(str(item.get("imageRef") or "").strip().lower().encode("utf-8")).hexdigest()[:24] if item.get("imageRef") else "",
                        dumps_json({**item, "diversity": diversity}), now, now,
                    ),
                )
    return get_weekly_growth_plan(root, week_start) or plan


def get_weekly_growth_plan(root: Path, week_start: str = "") -> dict[str, Any] | None:
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            if week_start:
                row = conn.execute("SELECT payload_json FROM weekly_growth_plans WHERE week_start=?", (week_start,)).fetchone()
            else:
                row = conn.execute("SELECT payload_json FROM weekly_growth_plans ORDER BY week_start DESC LIMIT 1").fetchone()
    if not row:
        return None
    payload = loads_json(row["payload_json"])
    return payload if isinstance(payload, dict) else None


def weekly_growth_history(root: Path, before_date: str = "", limit: int = 80) -> list[dict[str, Any]]:
    init_db(root)
    where = "WHERE slot_date < ?" if before_date else ""
    params: list[Any] = [before_date] if before_date else []
    params.append(max(1, min(500, int(limit or 80))))
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute(
                f"SELECT payload_json FROM weekly_growth_slots {where} ORDER BY slot_date DESC, slot_number DESC LIMIT ?",
                params,
            ).fetchall()
    result = []
    for row in rows:
        payload = loads_json(row["payload_json"])
        if isinstance(payload, dict):
            result.append(payload)
    return result


def recent_platform_post_history(root: Path, limit: int = 120) -> list[dict[str, Any]]:
    init_db(root)
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute(
                """
                SELECT platform, content_type, asset_folder, payload_json
                FROM platform_posts
                ORDER BY COALESCE(published_at, scheduled_at, created_at, updated_at) DESC
                LIMIT ?
                """,
                (max(1, min(500, int(limit or 120))),),
            ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        payload = loads_json(row["payload_json"] or "{}")
        payload = payload if isinstance(payload, dict) else {}
        caption = str(payload.get("caption") or payload.get("text") or payload.get("openingText") or "").strip()
        hook = caption.splitlines()[0].strip() if caption else str(payload.get("title") or "").strip()
        result.append({
            "hook": hook,
            "cta": str(payload.get("cta") or ""),
            "imageRef": str(payload.get("image") or payload.get("mediaPath") or row["asset_folder"] or ""),
            "platform": str(row["platform"] or ""),
            "contentType": str(row["content_type"] or ""),
        })
    return result


RELEASE_JOB_STATUSES = {"pending", "running", "retrying", "prepared", "verified", "blocked", "failed", "cancelled"}
RELEASE_JOB_STAGES = {"inner_disciple", "path_initiate", "royal_road"}


def release_job_key(abbr: str, chapter: int, stage: str, scheduled_for: str) -> str:
    normalized_abbr = str(abbr or "").strip().upper()
    normalized_stage = str(stage or "").strip().lower().replace("-", "_")
    return f"{normalized_abbr}-{int(chapter)}-{normalized_stage}-{str(scheduled_for or '').strip()}"


def enqueue_release_jobs(root: Path, jobs: list[dict[str, Any]]) -> dict[str, int]:
    init_db(root)
    inserted = 0
    existing = 0
    now = utc_now_text()
    with _LOCK:
        with connect(root) as conn:
            for raw in jobs:
                abbr = str(raw.get("abbr") or raw.get("novelAbbr") or "").strip().upper()
                chapter = int(raw.get("chapter") or raw.get("chapterNumber") or 0)
                stage = str(raw.get("stage") or "").strip().lower().replace("-", "_")
                scheduled_for = str(raw.get("scheduledFor") or raw.get("date") or "").strip()
                if not abbr or chapter <= 0 or stage not in RELEASE_JOB_STAGES or not scheduled_for:
                    continue
                key = release_job_key(abbr, chapter, stage, scheduled_for)
                job_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
                payload = dict(raw)
                payload.update({"jobId": job_id, "jobKey": key, "abbr": abbr, "chapter": chapter, "stage": stage, "scheduledFor": scheduled_for})
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO release_automation_jobs(
                        job_id, job_key, release_plan_id, novel_abbr, chapter_number, stage,
                        scheduled_for, status, attempt_count, max_attempts, next_attempt_at,
                        payload_json, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        job_id, key, str(raw.get("releasePlanId") or ""), abbr, chapter, stage,
                        scheduled_for, "pending", 0, max(1, int(raw.get("maxAttempts") or 3)), now,
                        dumps_json(payload), now, now,
                    ),
                )
                if cursor.rowcount:
                    inserted += 1
                else:
                    existing += 1
    return {"inserted": inserted, "existing": existing}


def list_release_jobs(root: Path, statuses: list[str] | None = None, limit: int = 500) -> list[dict[str, Any]]:
    init_db(root)
    normalized = [str(item or "").strip().lower() for item in (statuses or []) if str(item or "").strip().lower() in RELEASE_JOB_STATUSES]
    params: list[Any] = []
    where = ""
    if normalized:
        where = f"WHERE status IN ({','.join('?' for _ in normalized)})"
        params.extend(normalized)
    params.append(max(1, min(5000, int(limit or 500))))
    with _LOCK:
        with connect(root) as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM release_automation_jobs
                {where}
                ORDER BY CASE stage WHEN 'inner_disciple' THEN 0 WHEN 'path_initiate' THEN 1 ELSE 2 END,
                    scheduled_for, novel_abbr, chapter_number
                LIMIT ?
                """,
                params,
            ).fetchall()
    return [_release_job_row(row) for row in rows]


def _release_job_row(row: sqlite3.Row) -> dict[str, Any]:
    payload = loads_json(row["payload_json"]) or {}
    payload.update({
        "jobId": row["job_id"], "jobKey": row["job_key"], "releasePlanId": row["release_plan_id"] or "",
        "abbr": row["novel_abbr"], "chapter": int(row["chapter_number"]), "stage": row["stage"],
        "scheduledFor": row["scheduled_for"], "status": row["status"], "attemptCount": int(row["attempt_count"]),
        "maxAttempts": int(row["max_attempts"]), "workerId": row["worker_id"] or "",
        "nextAttemptAt": row["next_attempt_at"] or "", "startedAt": row["started_at"] or "",
        "completedAt": row["completed_at"] or "", "verifiedAt": row["verified_at"] or "",
        "remoteUrl": row["remote_url"] or "", "lastError": row["last_error"] or "",
        "screenshotPath": row["screenshot_path"] or "", "createdAt": row["created_at"], "updatedAt": row["updated_at"],
    })
    return payload


def claim_next_release_job(root: Path, worker_id: str) -> dict[str, Any] | None:
    init_db(root)
    now = utc_now_text()
    with _LOCK:
        with connect(root) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT job_id FROM release_automation_jobs
                WHERE release_automation_jobs.status IN ('pending','retrying')
                  AND release_automation_jobs.attempt_count < release_automation_jobs.max_attempts
                  AND (release_automation_jobs.next_attempt_at IS NULL OR release_automation_jobs.next_attempt_at='' OR release_automation_jobs.next_attempt_at<=?)
                  AND NOT EXISTS (
                    SELECT 1
                    FROM release_automation_jobs AS prerequisite
                    WHERE prerequisite.novel_abbr=release_automation_jobs.novel_abbr
                      AND prerequisite.chapter_number=release_automation_jobs.chapter_number
                      AND prerequisite.status!='verified'
                      AND (
                        (release_automation_jobs.stage='path_initiate' AND prerequisite.stage='inner_disciple')
                        OR (release_automation_jobs.stage='royal_road' AND prerequisite.stage IN ('inner_disciple','path_initiate'))
                      )
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM release_automation_jobs AS phase_prerequisite
                    WHERE phase_prerequisite.status NOT IN ('verified','cancelled')
                      AND (
                        (release_automation_jobs.stage='path_initiate' AND phase_prerequisite.stage='inner_disciple')
                        OR (release_automation_jobs.stage='royal_road' AND phase_prerequisite.stage IN ('inner_disciple','path_initiate'))
                      )
                  )
                ORDER BY CASE stage WHEN 'inner_disciple' THEN 0 WHEN 'path_initiate' THEN 1 ELSE 2 END,
                    scheduled_for, novel_abbr, chapter_number
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                """UPDATE release_automation_jobs
                   SET status='running', worker_id=?, attempt_count=attempt_count+1,
                       started_at=?, last_error='', updated_at=? WHERE job_id=?""",
                (worker_id, now, now, row["job_id"]),
            )
            claimed = conn.execute("SELECT * FROM release_automation_jobs WHERE job_id=?", (row["job_id"],)).fetchone()
            conn.commit()
    return _release_job_row(claimed) if claimed else None


def update_release_job(root: Path, job_id: str, status: str, **fields: Any) -> dict[str, Any] | None:
    init_db(root)
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in RELEASE_JOB_STATUSES:
        raise ValueError(f"Unsupported release job status: {status}")
    now = utc_now_text()
    allowed = {
        "workerId": "worker_id", "nextAttemptAt": "next_attempt_at", "completedAt": "completed_at",
        "verifiedAt": "verified_at", "remoteUrl": "remote_url", "lastError": "last_error",
        "screenshotPath": "screenshot_path",
    }
    assignments = ["status=?", "updated_at=?"]
    values: list[Any] = [normalized_status, now]
    for key, column in allowed.items():
        if key in fields:
            assignments.append(f"{column}=?")
            values.append(fields[key])
    if normalized_status in {"prepared", "verified", "cancelled"} and "completedAt" not in fields:
        assignments.append("completed_at=?")
        values.append(now)
    if normalized_status == "verified" and "verifiedAt" not in fields:
        assignments.append("verified_at=?")
        values.append(now)
    with _LOCK:
        with connect(root) as conn:
            if "payloadUpdates" in fields:
                current = conn.execute(
                    "SELECT payload_json FROM release_automation_jobs WHERE job_id=?",
                    (str(job_id),),
                ).fetchone()
                payload = loads_json(current["payload_json"]) if current and current["payload_json"] else {}
                if not isinstance(payload, dict):
                    payload = {}
                updates = fields.get("payloadUpdates")
                if isinstance(updates, dict):
                    payload.update(updates)
                assignments.append("payload_json=?")
                values.append(dumps_json(payload))
            values.append(str(job_id))
            conn.execute(f"UPDATE release_automation_jobs SET {', '.join(assignments)} WHERE job_id=?", values)
            row = conn.execute("SELECT * FROM release_automation_jobs WHERE job_id=?", (str(job_id),)).fetchone()
    return _release_job_row(row) if row else None


def reset_release_jobs_after_systemic_failure(root: Path, error_marker: str) -> int:
    """Return untouched release jobs to pending after one shared environment failure."""
    init_db(root)
    marker = str(error_marker or "").strip()
    if not marker:
        return 0
    now = utc_now_text()
    with _LOCK:
        with connect(root) as conn:
            cursor = conn.execute(
                """
                UPDATE release_automation_jobs
                SET status='pending', attempt_count=0, worker_id='', next_attempt_at='',
                    started_at='', last_error='', updated_at=?
                WHERE status='retrying' AND last_error LIKE ?
                  AND COALESCE(completed_at, '')='' AND COALESCE(verified_at, '')=''
                """,
                (now, f"%{marker}%"),
            )
            return int(cursor.rowcount or 0)


def recover_stale_release_jobs(root: Path, stale_before: str) -> int:
    init_db(root)
    now = utc_now_text()
    with _LOCK:
        with connect(root) as conn:
            cursor = conn.execute(
                """
                UPDATE release_automation_jobs
                SET status=CASE WHEN attempt_count < max_attempts THEN 'retrying' ELSE 'failed' END,
                    worker_id='', next_attempt_at=?, last_error='Worker stopped before completion.', updated_at=?
                WHERE status='running' AND started_at<?
                """,
                (now, now, str(stale_before)),
            )
    return int(cursor.rowcount or 0)
