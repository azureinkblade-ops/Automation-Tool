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
    apply_depiction_gate,
    apply_gray_look_hold,
    apply_x_default,
    ensure_hold_reasons,
    is_weekday,
    load_live_chapter_records,
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
    HOLD_GRAY_LOOK_UNDECIDED,
    OVERRIDE_RELATIVE,
    PUBLISH_GENERATED_MEDIA,
    STATUS_HELD,
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
    apply_media_required_holds,
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


def _media_for_item(
    item: CadenceItem,
    by_chapter: Mapping[tuple[str, int], Path] | None,
    by_novel: Mapping[str, Path] | None,
) -> Path | None:
    if item.source_chapter is not None and by_chapter:
        path = by_chapter.get((item.novel, int(item.source_chapter)))
        if path is not None:
            return Path(path)
    if by_novel:
        path = by_novel.get(item.novel)
        if path is not None:
            return Path(path)
    return None


def attach_media(
    items: Sequence[CadenceItem],
    *,
    day_path: Path,
    stills: Mapping[str, Path],
    clips: Mapping[str, Path],
    share_still: bool,
    stills_by_chapter: Mapping[tuple[str, int], Path] | None = None,
    clips_by_chapter: Mapping[tuple[str, int], Path] | None = None,
) -> None:
    used: set[str] = set()
    copied: dict[Path, str] = {}

    def _copy(source: Path, *, novel: str, role: str) -> str | None:
        if not source.is_file():
            return None
        resolved = source.resolve()
        if resolved in copied:
            return copied[resolved]
        relative = unique_media_name(source, novel=novel, role=role, used=used)
        copy_media_file(source, day_path, relative)
        copied[resolved] = relative
        return relative

    for item in items:
        if item.platform in {"facebook", "instagram"}:
            source = _media_for_item(item, stills_by_chapter, stills)
            if source is None:
                continue
            relative = _copy(source, novel=item.novel, role="still")
            if relative:
                item.media = [relative]
        elif item.platform == "tiktok":
            source = _media_for_item(item, clips_by_chapter, clips)
            if source is None:
                continue
            relative = _copy(source, novel=item.novel, role="tiktok")
            if relative:
                item.media = [relative]


def apply_stage(
    items: list[CadenceItem],
    *,
    stage: str,
    dry_run: bool,
    config: WeekdayCadenceConfig,
    now: datetime,
    deadline: datetime,
    identity_needed: Mapping[str, bool] | None = None,
    identity_approved: Mapping[str, bool] | None = None,
    stills: Mapping[Any, Path],
    produce_clip=None,
    pipeline_depiction=None,
) -> list[CadenceItem]:
    """Apply media (TikTok) first, then the per-item depiction gate.

    identity_needed is ignored: approval is never inferred from novel membership.
    identity_approved may still clear a governed item, keyed by item id then novel.
    """
    del identity_needed  # never a novel-membership gate
    approved_map = dict(identity_approved or {})
    updated: list[CadenceItem] = []
    for item in items:
        if item.platform == "x":
            updated.append(apply_x_default(item, config))
            continue
        if (
            item.platform == "tiktok"
            and stage in {"encode", "pack"}
            and str(item.hold_reason or "") != HOLD_GRAY_LOOK_UNDECIDED
        ):
            # Governed items still get their clip made, then are held for approval.
            tiktok_still = stills.get(item.novel)
            if item.source_chapter is not None:
                tiktok_still = stills.get((item.novel, int(item.source_chapter)), tiktok_still)
            item, _clip = build_tiktok_item(
                item,
                still=tiktok_still,
                approved=True,
                config=config,
                produce_clip=None if dry_run else produce_clip,
                dry_run=dry_run,
            )
        approved = bool(approved_map.get(item.id) or approved_map.get(item.novel, False))
        still = stills.get(item.novel)
        sidecar = None
        if pipeline_depiction is not None:
            sidecar = pipeline_depiction(item, still)
        else:
            try:
                from tools.weekday_cadence_media import depiction_from_still
                sidecar = depiction_from_still(still)
            except Exception:
                sidecar = None
        item = apply_depiction_gate(
            item,
            approved=approved,
            now=now,
            deadline=deadline,
            pipeline_depiction=sidecar,
        )
        item = apply_gray_look_hold(item)
        updated.append(item)
    return ensure_hold_reasons(updated)


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
    with_media: bool = False,
    still_finder=None,
    generate_still=None,
    gpu_lease=None,
    media_port_free=None,
    media_processes=None,
    bible_preflight=None,
    ensure_comfy=None,
    stop_comfy=None,
) -> dict[str, Any]:
    if config.publish_generated_media or PUBLISH_GENERATED_MEDIA:
        raise RuntimeError("weekday cadence refused to run with publishing enabled")
    if not is_weekday(target):
        raise ValueError(f"{target.isoformat()} is not a Monday-Friday cadence day")
    current = now_now(config, now)
    deadline = approval_deadline_for(target, config)
    planned, picks = plan_day_items(
        records,
        config,
        captions_by_novel=captions_by_novel,
        overrides=overrides,
        bank=list(copy_bank or []),
        target=target,
        weekday=weekday_name(target),
        default_tz=current.tzinfo,
    )
    planned = [apply_gray_look_hold(item) for item in planned]
    stills = dict(stills or {})
    clips = dict(clips or {})
    stills_by_chapter: dict[tuple[str, int], Path] = {}
    tiktok_stills: dict[tuple[str, int], Path] = {}
    clips_by_chapter: dict[tuple[str, int], Path] = {}
    identity_needed = dict(identity_needed or {})
    identity_approved = dict(identity_approved or {})
    if with_media and not dry_run:
        from tools.weekday_cadence_media import check_bible_media_preflight

        # Fail before mkdir or save_day_bundle so an existing day pack is not overwritten.
        checker = bible_preflight if bible_preflight is not None else check_bible_media_preflight
        checker()

    if with_media:
        from tools.weekday_cadence_media import prepare_media

        work_dir = day_dir(out_root, target.isoformat(), output_dirname=config.output_dirname) / "media"
        work_dir.mkdir(parents=True, exist_ok=True)
        production_still = not dry_run and generate_still is None
        if production_still:
            from tools.weekday_cadence_stills import generate_cadence_still

            planned_items = planned

            from tools.weekday_cadence_stills import STILL_SIZE_FB_IG, STILL_SIZE_TIKTOK

            def generate_still(novel, chapter, size=STILL_SIZE_FB_IG, _items=planned_items, _work=work_dir):
                def _usable(row):
                    return (
                        row.novel == novel
                        and row.source_chapter == chapter
                        and row.platform != "x"
                        and str(getattr(row, "hold_reason", "") or "") != HOLD_GRAY_LOOK_UNDECIDED
                    )

                tiktok = tuple(size) == tuple(STILL_SIZE_TIKTOK)
                preferred = ("tiktok",) if tiktok else ("facebook", "instagram")
                match = next((row for row in _items if _usable(row) and row.platform in preferred), None)
                if match is None:
                    match = next((row for row in _items if _usable(row)), None)
                role = "tiktok" if tuple(size) == tuple(STILL_SIZE_TIKTOK) else "still"
                return generate_cadence_still(
                    novel,
                    chapter,
                    target=_work / f"{novel}-{chapter}-{role}.png",
                    visual=getattr(match, "visual", "") if match else "",
                    depiction=getattr(match, "depiction", "") if match else "",
                    caption=getattr(match, "caption", "") if match else "",
                    size=size,
                )

        if not dry_run and produce_clip is None:
            from tools.weekday_cadence_stills import CadenceClipAdapter

            produce_clip = CadenceClipAdapter(store_root=work_dir)

        if production_still and ensure_comfy is None:
            from tools.weekday_cadence_media import (
                ensure_cadence_comfy,
                stop_cadence_comfy_if_started,
            )

            ensure_comfy = ensure_cadence_comfy
            if stop_comfy is None:
                stop_comfy = stop_cadence_comfy_if_started

        prepared = prepare_media(
            novels=tuple({item.novel for item in planned}),
            chapters={
                item.novel: item.source_chapter
                for item in planned
                if item.platform != "x" and item.source_chapter is not None
            },
            with_media=True,
            dry_run=dry_run,
            existing_stills=stills,
            finder=still_finder,
            generate_still=None if dry_run else generate_still,
            produce_clip=None if dry_run else produce_clip,
            gpu_lease=gpu_lease,
            port_free=media_port_free,
            processes=media_processes,
            items=planned,
            output_dir=work_dir,
            acquire_lease=gpu_lease is not None or (not dry_run and produce_clip is not None and gpu_lease is not None),
            ensure_comfy=None if dry_run else ensure_comfy,
            stop_comfy=None if dry_run else stop_comfy,
        )
        stills.update(prepared.stills)
        clips.update(prepared.clips)
        stills_by_chapter = dict(prepared.stills_by_chapter)
        tiktok_stills = dict(prepared.tiktok_stills)
        clips_by_chapter = dict(prepared.clips_by_chapter)
        for item in planned:
            if item.platform == "x" or item.source_chapter is None:
                continue
            reason = prepared.generation_holds.get((item.novel, int(item.source_chapter)))
            if not reason:
                continue
            item.status = STATUS_HELD
            item.hold_reason = reason
    bank_items = list(copy_bank or [])
    provided = dict(captions_by_novel or {})
    for item in planned:
        if item.source_chapter is None:
            continue
        fallback = (provided.get(item.novel) or {}).get(item.platform) or default_captions(
            item.novel, item.source_chapter, item.source_platform
        ).get(item.platform, "")
        caps = captions_for_novel(
            novel=item.novel,
            chapter=item.source_chapter,
            source_platform=item.source_platform,
            weekday=weekday_name(target),
            bank=bank_items,
            allowed_chapters=[item.source_chapter],
            fallback={item.platform: fallback} if fallback else default_captions(item.novel, item.source_chapter, item.source_platform),
            live_tiers=item.live_tiers,
        )
        if caps.get(item.platform):
            item.caption = caps[item.platform]
        elif not item.caption:
            item.caption = fallback
    stage_stills: dict[Any, Path] = dict(stills)
    stage_stills.update(tiktok_stills)
    planned = apply_stage(
        planned,
        stage=stage,
        dry_run=dry_run,
        config=config,
        now=current,
        deadline=deadline,
        identity_needed=identity_needed,
        identity_approved=identity_approved,
        stills=stage_stills,
        produce_clip=produce_clip if not dry_run else stub_produce_clip,
    )
    day_path = day_dir(out_root, target.isoformat(), output_dirname=config.output_dirname)
    day_path.mkdir(parents=True, exist_ok=True)
    attach_media(
        planned,
        day_path=day_path,
        stills=stills,
        clips=clips,
        share_still=config.share_still_across_static,
        stills_by_chapter=stills_by_chapter,
        clips_by_chapter=clips_by_chapter,
    )
    apply_media_required_holds(planned)
    ensure_hold_reasons(planned)
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
    parser.add_argument("--app-root", help="Root that holds local chapter_ledger records (read-only).")
    parser.add_argument(
        "--chapter-source",
        choices=("patreon", "royal_road"),
        default=None,
        help="Override chapter source. Default: patreon (verified live records only).",
    )
    parser.add_argument("--source-commit", default="", help="Commit SHA recorded on the manifest.")
    parser.add_argument("--copy-bank", help="Optional Writer copy-bank markdown path.")
    parser.add_argument("--overrides", help="Optional patreon_live_overrides.json path.")
    parser.add_argument(
        "--chapter-pick",
        choices=("bank_day", "newest_live"),
        default=None,
        help="Chapter pick mode. Default: bank_day rotation. newest_live keeps the previous behavior.",
    )
    parser.add_argument(
        "--bank-day-start",
        default=None,
        help="Monday that is bank day 1 (YYYY-MM-DD). Default: 2026-11-23.",
    )
    parser.add_argument("--timezone", default=None)
    parser.add_argument(
        "--with-media",
        action="store_true",
        dest="with_media",
        help=(
            "Resolve or generate stills and Wan clips. Reuses existing promo or "
            "approved stills first. Takes the GPU through the existing lease only "
            "when port 8188 is free and no Research python/ffmpeg process is running. "
            "Do not combine with a live Research GPU test. --dry-run never generates."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.root).resolve() if args.root else _repo_root()
    app_root = Path(args.app_root).resolve() if args.app_root else repo
    cfg_data: dict[str, Any] = {}
    if args.chapter_source:
        cfg_data["chapter_source"] = args.chapter_source
    if getattr(args, "chapter_pick", None):
        cfg_data["chapter_pick"] = args.chapter_pick
    if getattr(args, "bank_day_start", None):
        cfg_data["bank_day_start"] = args.bank_day_start
    if args.timezone:
        cfg_data["timezone"] = args.timezone
    config = WeekdayCadenceConfig.from_mapping(cfg_data)
    today = now_now(config).date()
    target = parse_iso_date(args.date) if args.date else next_weekday(today)
    records = load_live_chapter_records(app_root)
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
    try:
        payload = run_cadence(
            target=target,
            stage=args.stage,
            dry_run=bool(args.dry_run),
            config=config,
            out_root=repo,
            records=records,
            source_commit=args.source_commit or _git_commit(repo),
            produce_clip=(
                stub_produce_clip
                if bool(args.dry_run) or not bool(getattr(args, "with_media", False))
                else None
            ),
            overrides=load_patreon_live_overrides(override_path),
            copy_bank=load_copy_bank(bank_path),
            with_media=bool(getattr(args, "with_media", False)),
        )
    except Exception as exc:
        from tools.weekday_cadence_media import CadenceMediaPreflightError

        if not isinstance(exc, CadenceMediaPreflightError):
            raise
        message = str(exc)
        print(message)
        print(message, file=sys.stderr)
        return 1
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
            f"newest {abbr} chapter={pick.get('source_chapter')} "
            f"source={pick.get('source_platform')} verified={pick.get('verified')} "
            f"tiers={','.join(pick.get('live_tiers') or [])} "
            f"went_live={pick.get('went_live_at') or ''} "
            f"hold={pick.get('hold_reason') or ''}"
        )
    for item in payload.get("items") or []:
        print(
            f"item {item.get('id')} ch={item.get('source_chapter')} "
            f"rule={item.get('pick_rule') or ''} day={item.get('bank_day')} "
            f"copy={item.get('copy_source') or ''}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
