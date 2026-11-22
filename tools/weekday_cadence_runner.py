"""CLI for the weekday social cadence (phase 1).

Writes a self-contained daily-social/<date>/ folder with manifest.json, manifest.md,
manifest.csv, and copies of any provided media. Dry-run never calls ComfyUI, ffmpeg,
Buffer, or social APIs. Publish stays off.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from typing import Any, Mapping, Sequence

from tools.weekday_cadence import (
    approval_deadline_for,
    approval_inbox_entries,
    apply_identity_cutoff,
    is_weekday,
    load_release_status_records,
    next_weekday,
    now_now,
    parse_iso_date,
    plan_day_items,
    weekday_name,
)
from tools.weekday_cadence_captions import captions_for_novel, load_copy_bank
from tools.weekday_cadence_config import (
    COPY_BANK_RELATIVE,
    OVERRIDE_RELATIVE,
    PUBLISH_GENERATED_MEDIA,
    WeekdayCadenceConfig,
)
from tools.weekday_cadence_overrides import load_patreon_live_overrides
from tools.weekday_cadence_manifest import (
    CadenceItem,
    build_manifest,
    copy_media_file,
    day_dir,
    load_manifest,
    save_day_bundle,
    unique_media_name,
)
from tools.weekday_cadence_posts import (
    apply_shared_still,
    build_tiktok_item,
    default_captions,
    stub_produce_clip,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_commit(root: Path) -> str:
    try:
        import subprocess

        text = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
        return text.strip()
    except Exception:
        return ""


def format_timestamp(value: datetime) -> str:
    return value.isoformat()


def attach_media(
    items: Sequence[CadenceItem],
    *,
    day_path: Path,
    stills: Mapping[str, Path],
    clips: Mapping[str, Path],
    share_still: bool,
) -> None:
    used: set[str] = set()
    for novel, source in stills.items():
        if not source.is_file():
            continue
        relative = unique_media_name(source, novel=novel, role="still", used=used)
        copy_media_file(source, day_path, relative)
        novel_items = [item for item in items if item.novel == novel]
        if share_still:
            apply_shared_still(novel_items, relative)
        else:
            apply_shared_still(novel_items, relative)
    for novel, source in clips.items():
        if not source.is_file():
            continue
        relative = unique_media_name(source, novel=novel, role="tiktok", used=used)
        copy_media_file(source, day_path, relative)
        for item in items:
            if item.novel == novel and item.platform == "tiktok":
                item.media = [relative]


def apply_stage(
    items: list[CadenceItem],
    *,
    stage: str,
    dry_run: bool,
    config: WeekdayCadenceConfig,
    now: datetime,
    deadline: datetime,
    identity_needed: Mapping[str, bool],
    identity_approved: Mapping[str, bool],
    stills: Mapping[str, Path],
    produce_clip=None,
) -> list[CadenceItem]:
    updated: list[CadenceItem] = []
    for item in items:
        needs = bool(identity_needed.get(item.novel, False))
        approved = bool(identity_approved.get(item.novel, False))
        item = apply_identity_cutoff(
            item,
            needs_approval=needs,
            approved=approved,
            now=now,
            deadline=deadline,
        )
        if item.platform == "tiktok" and stage in {"encode", "pack"}:
            item, _clip = build_tiktok_item(
                item,
                still=stills.get(item.novel),
                approved=approved or not needs,
                config=config,
                produce_clip=None if dry_run else produce_clip,
                dry_run=dry_run,
            )
        updated.append(item)
    return updated


def run_cadence(
    *,
    target: date,
    stage: str,
    dry_run: bool,
    config: WeekdayCadenceConfig,
    out_root: Path,
    records: Mapping[str, Any] | None,
    source_commit: str = "",
    now: datetime | None = None,
    stills: Mapping[str, Path] | None = None,
    clips: Mapping[str, Path] | None = None,
    identity_needed: Mapping[str, bool] | None = None,
    identity_approved: Mapping[str, bool] | None = None,
    produce_clip=None,
    captions_by_novel: Mapping[str, Mapping[str, str]] | None = None,
    overrides=None,
    copy_bank=None,
) -> dict[str, Any]:
    if config.publish_generated_media or PUBLISH_GENERATED_MEDIA:
        raise RuntimeError("weekday cadence refused to run with publishing enabled")
    if not is_weekday(target):
        raise ValueError(f"{target.isoformat()} is not a Monday-Friday cadence day")
    current = now_now(config, now)
    deadline = approval_deadline_for(target, config)
    planned, picks = plan_day_items(
        records, config, captions_by_novel=captions_by_novel, overrides=overrides
    )
    bank_items = list(copy_bank or [])
    by_novel: dict[str, dict[str, str]] = dict(captions_by_novel or {})
    for novel, pick in picks.items():
        allowed = [pick.chapter] if pick.chapter is not None else []
        fallback = by_novel.get(novel) or default_captions(novel, pick.chapter, pick.source_platform)
        by_novel[novel] = captions_for_novel(
            novel=novel,
            chapter=pick.chapter,
            source_platform=pick.source_platform,
            weekday=weekday_name(target),
            bank=bank_items,
            allowed_chapters=allowed,
            fallback=fallback,
        )
    for item in planned:
        caps = by_novel.get(item.novel) or {}
        if caps.get(item.platform):
            item.caption = caps[item.platform]
        elif not item.caption:
            item.caption = default_captions(item.novel, item.source_chapter, item.source_platform).get(item.platform, "")
    planned = apply_stage(
        planned,
        stage=stage,
        dry_run=dry_run,
        config=config,
        now=current,
        deadline=deadline,
        identity_needed=identity_needed or {},
        identity_approved=identity_approved or {},
        stills=stills or {},
        produce_clip=produce_clip if not dry_run else stub_produce_clip,
    )
    day_path = day_dir(out_root, target.isoformat(), output_dirname=config.output_dirname)
    day_path.mkdir(parents=True, exist_ok=True)
    attach_media(
        planned,
        day_path=day_path,
        stills=stills or {},
        clips=clips or {},
        share_still=config.share_still_across_static,
    )
    payload = build_manifest(
        target_date=target.isoformat(),
        target_weekday=weekday_name(target),
        items=planned,
        config=config,
        generated_at=format_timestamp(current),
        approval_deadline=format_timestamp(deadline),
        source_commit=source_commit,
        extra={
            "stage": stage,
            "dryRun": bool(dry_run),
            "chapterPicks": {abbr: pick.to_dict() for abbr, pick in picks.items()},
            "identityBatch": approval_inbox_entries(
                planned, approval_deadline=format_timestamp(deadline)
            ),
        },
    )
    existing = None
    manifest_path = day_path / "manifest.json"
    if manifest_path.exists():
        existing = load_manifest(manifest_path)
    saved = save_day_bundle(day_path, payload, existing=existing)
    saved["_dayDir"] = str(day_path)
    return saved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a weekday social cadence folder (phase 1, no publishing).")
    parser.add_argument("--date", help="Target weekday YYYY-MM-DD. Default: next Mon-Fri after today.")
    parser.add_argument(
        "--stage",
        choices=("stills", "approve-cut", "encode", "pack"),
        default="pack",
        help="Pipeline stage. encode/pack stub the clip unless --dry-run is off and a producer is injected.",
    )
    parser.add_argument("--dry-run", action="store_true", help="No ComfyUI, no ffmpeg, no API calls.")
    parser.add_argument("--root", help="Repo root used for the daily-social output folder.")
    parser.add_argument("--app-root", help="Root that holds local release-status records (read-only).")
    parser.add_argument(
        "--chapter-source",
        choices=("patreon", "royal_road"),
        default=None,
        help="Override chapter source. Default: patreon (verified live records only).",
    )
    parser.add_argument("--source-commit", default="", help="Commit SHA recorded on the manifest.")
    parser.add_argument("--copy-bank", help="Optional Writer copy-bank markdown path.")
    parser.add_argument("--overrides", help="Optional patreon_live_overrides.json path.")
    parser.add_argument("--timezone", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.root).resolve() if args.root else _repo_root()
    app_root = Path(args.app_root).resolve() if args.app_root else repo
    cfg_data: dict[str, Any] = {}
    if args.chapter_source:
        cfg_data["chapter_source"] = args.chapter_source
    if args.timezone:
        cfg_data["timezone"] = args.timezone
    config = WeekdayCadenceConfig.from_mapping(cfg_data)
    today = now_now(config).date()
    target = parse_iso_date(args.date) if args.date else next_weekday(today)
    records = load_release_status_records(app_root)
    override_path = Path(args.overrides).resolve() if getattr(args, "overrides", None) else repo / OVERRIDE_RELATIVE
    if args.app_root:
        # Prefer the output repo copy; fall back to the records root if needed.
        alt = app_root / OVERRIDE_RELATIVE
        if not override_path.is_file() and alt.is_file():
            override_path = alt
    bank_path = Path(args.copy_bank).resolve() if getattr(args, "copy_bank", None) else repo / COPY_BANK_RELATIVE
    if not bank_path.is_file():
        alt_bank = app_root / COPY_BANK_RELATIVE
        if alt_bank.is_file():
            bank_path = alt_bank
    payload = run_cadence(
        target=target,
        stage=args.stage,
        dry_run=bool(args.dry_run),
        config=config,
        out_root=repo,
        records=records,
        source_commit=args.source_commit or _git_commit(repo),
        produce_clip=stub_produce_clip,
        overrides=load_patreon_live_overrides(override_path),
        copy_bank=load_copy_bank(bank_path),
    )
    day = payload.get("_dayDir", "")
    summary = payload.get("summary") or {}
    print(f"targetDate={payload.get('targetDate')} weekday={payload.get('targetWeekday')}")
    print(f"dayDir={day}")
    print(
        "summary "
        f"status={payload.get('status')} "
        f"ready={summary.get('ready')} held={summary.get('held')} "
        f"awaiting_approval={summary.get('awaiting_approval')} "
        f"awaiting_david_post={summary.get('awaiting_david_post')}"
    )
    picks = payload.get("chapterPicks") or {}
    for abbr, pick in picks.items():
        print(
            f"pick {abbr} chapter={pick.get('source_chapter')} "
            f"source={pick.get('source_platform')} verified={pick.get('verified')} "
            f"hold={pick.get('hold_reason') or ''}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
