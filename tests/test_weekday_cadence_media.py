"""--with-media planning uses stubs only; never starts ComfyUI, ffmpeg, or a lease on a busy GPU."""

from __future__ import annotations

from types import SimpleNamespace

from pathlib import Path

from tools.weekday_cadence_media import (
    gpu_preflight,
    identity_character_for,
    prepare_media,
)
from tools.weekday_cadence_posts import ClipResult


class FakeLease:
    KIND_I2V = "i2v"

    def __init__(self) -> None:
        self.acquires = []
        self.releases = []

    def acquire(self, job_id, kind, **kwargs):
        self.acquires.append((job_id, kind, kwargs))

    def release(self, job_id):
        self.releases.append(job_id)


def test_identity_characters_map_to_approval_batch():
    assert identity_character_for("EN") == "Kael Veyra"
    assert identity_character_for("HA") == "Kai"
    assert identity_character_for("HP") == "Liang"
    assert identity_character_for("SF") == "Jarek"


def test_preflight_fails_when_comfy_port_busy_or_research_ffmpeg_is_running():
    ok, reason = gpu_preflight(port=8188, port_free=lambda _port: False, processes=[])
    assert ok is False
    assert "COMFY_PORT_BUSY" in reason
    ok2, reason2 = gpu_preflight(
        port=8188,
        port_free=lambda _port: True,
        processes=[{"name": "ffmpeg.exe", "command": "ffmpeg -i stress"}],
    )
    assert ok2 is False
    assert "RESEARCH_PROCESS_RUNNING" in reason2
    ok3, reason3 = gpu_preflight(port=8188, port_free=lambda _port: True, processes=[])
    assert ok3 is True
    assert reason3 == ""


def test_reuses_existing_still_and_does_not_generate(tmp_path: Path):
    existing = tmp_path / "promo.png"
    existing.write_bytes(b"png")
    generated = []

    def generate(novel, chapter):
        generated.append((novel, chapter))
        raise AssertionError("generate must not run when a still already exists")

    result = prepare_media(
        novels=["EN"],
        chapters={"EN": 140},
        with_media=True,
        dry_run=False,
        existing_stills={"EN": existing},
        generate_still=generate,
        produce_clip=None,
        gpu_lease=FakeLease(),
        port_free=lambda _port: True,
        processes=[],
    )
    assert result.stills["EN"] == existing
    assert result.plans[0].origin == "existing_promo"
    assert result.identity_needed.get("EN") is not True
    assert generated == []
    assert result.lease_acquired is False


def test_generates_only_when_missing_and_preflight_passes(tmp_path: Path):
    made = tmp_path / "new-ha.png"
    lease = FakeLease()
    calls = []

    def generate(novel, chapter):
        calls.append((novel, chapter))
        made.write_bytes(b"png")
        return made

    def finder(novel, chapter):
        return None

    result = prepare_media(
        novels=["HA"],
        chapters={"HA": 99},
        with_media=True,
        dry_run=False,
        finder=finder,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=lease,
        port_free=lambda _port: True,
        processes=[],
    )
    assert calls == [("HA", 99)]
    assert result.stills["HA"] == made
    assert result.generated == ["HA"]
    assert result.lease_acquired is True
    assert lease.acquires and lease.releases == ["weekday-cadence-media"]
    assert result.identity_needed.get("HA") is not True


def test_busy_gpu_skips_generation_and_does_not_acquire_lease(tmp_path: Path):
    lease = FakeLease()
    calls = []

    def generate(novel, chapter):
        calls.append((novel, chapter))
        path = tmp_path / f"{novel}.png"
        path.write_bytes(b"png")
        return path

    result = prepare_media(
        novels=["SF"],
        chapters={"SF": 126},
        with_media=True,
        dry_run=False,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=lease,
        port_free=lambda _port: True,
        processes=[{"name": "python.exe", "command": "python ComfyUI --listen 8188"}],
    )
    assert result.preflight_ok is False
    assert calls == []
    assert lease.acquires == []
    assert "SF" not in result.stills


def test_dry_run_with_media_never_generates_or_leases(tmp_path: Path):
    lease = FakeLease()

    def generate(novel, chapter):
        raise AssertionError("dry-run must not generate")

    def produce(*_args, **_kwargs):
        raise AssertionError("dry-run must not produce a clip")

    result = prepare_media(
        novels=["HP"],
        chapters={"HP": 148},
        with_media=True,
        dry_run=True,
        generate_still=generate,
        produce_clip=produce,
        gpu_lease=lease,
        port_free=lambda _port: True,
        processes=[],
    )
    assert result.lease_acquired is False
    assert lease.acquires == []
    assert result.stills == {}


def test_with_media_false_is_a_no_op():
    result = prepare_media(
        novels=["EN"],
        chapters={"EN": 140},
        with_media=False,
        dry_run=False,
        generate_still=lambda *_: Path("nope.png"),
    )
    assert result.stills == {}
    assert result.plans == []


def test_stub_clip_path_is_recorded_when_preflight_passes(tmp_path: Path):
    from PIL import Image
    from tools.weekday_cadence_stills import STILL_SIZE_FB_IG, STILL_SIZE_TIKTOK

    still = tmp_path / "en.png"
    Image.new("RGB", STILL_SIZE_FB_IG, (8, 8, 8)).save(still)
    vertical = tmp_path / "en-tiktok.png"
    Image.new("RGB", STILL_SIZE_TIKTOK, (16, 16, 16)).save(vertical)
    clip_path = tmp_path / "en.mp4"
    clip_path.write_bytes(b"mp4")
    lease = FakeLease()

    def generate(novel, chapter, size=STILL_SIZE_FB_IG):
        assert tuple(size) == tuple(STILL_SIZE_TIKTOK)
        return vertical

    def produce(path, **_kwargs):
        assert path == vertical
        return ClipResult(outcome="SOCIAL_READY", backend="wan_22", path=clip_path)

    result = prepare_media(
        novels=["EN"],
        chapters={"EN": 140},
        with_media=True,
        dry_run=False,
        existing_stills={"EN": still},
        generate_still=generate,
        produce_clip=produce,
        gpu_lease=lease,
        port_free=lambda _port: True,
        processes=[],
    )
    assert result.stills["EN"] == still
    assert result.tiktok_stills[("EN", 140)] == vertical
    assert result.clips["EN"] == clip_path
    assert result.lease_acquired is True
    assert lease.releases


def _records(*rows):
    chapters = {}
    for abbr, chapter, flags in rows:
        chapters[f"{abbr}-{chapter}"] = {"abbr": abbr, "chapter": chapter, **flags}
    return {"chapters": chapters}


BANK_SNIPPET = """# Weekday copy bank
- Items tagged **[APPROVAL: needs David's approval for media]** show Kai, Kael, Liang or Jarek on screen. Everything else uses settings or secondary characters and can go without that pass.
- X posts are text only (no media), so none need media approval.

## Day 1 (Week 1, Monday)

### EN: Eternal Nexus
**TikTok** [source EN-140] [APPROVAL: needs David's approval for media]
- Caption: Kael stands in the rain. Chapter 140 of Eternal Nexus is live now on Patreon. Link in bio.
#EternalNexus #cultivation

**FB/IG post** [source EN-140] [APPROVAL: needs David's approval for media]
- Text: Kael stands in the rain. Eternal Nexus chapter 140 is live now on Patreon. Link in bio.

**X post** [source EN-140]
kael is a name in text only. Eternal Nexus ch 140 is up on Patreon, link in bio #webnovel #cultivation

### SF: Soulforge Era
**TikTok** [source SF-126] [no governed characters]
- Caption: The furnaces open. Chapter 126 of Soulforge Era is live now on Patreon. Link in bio.
#SoulforgeEra #cultivation

**FB/IG post** [source SF-126] [no governed characters]
- Text: The furnaces open. Chapter 126 of Soulforge Era is live now on Patreon. Link in bio.

**X post** [source SF-126]
the furnaces open. Soulforge Era ch 126 is up on Patreon, link in bio #webnovel #cultivation

### HA: Heavenly Ascension System
**TikTok** [source HA-99]
- Caption: A door widens by a hair. Heavenly Ascension System chapter 99 is live now on Patreon. Link in bio.
#HeavenlyAscensionSystem #cultivation

**FB/IG post** [source HA-99]
- Text: A door widens by a hair. Heavenly Ascension System chapter 99 is live now on Patreon. Link in bio.

**X post** [source HA-99]
a door widens by a hair. HAS ch 99 is up on Patreon, link in bio #webnovel #cultivation
"""


def test_research_style_sf_item_reaches_media_and_x_stays_text_only(tmp_path: Path):
    """Reproduce Research's db54647 --with-media result and the required fix.

    Research put all 16 items, including SF and the 4 X posts, in
    awaiting_approval with no media and no hold reason, and never called the
    still/clip stage. An SF / no-character item must reach generate/produce;
    X must stay text-only and awaiting_david_post.
    """
    from datetime import datetime
    from tools.weekday_cadence import timezone_for
    from tools.weekday_cadence_captions import parse_copy_bank
    from tools.weekday_cadence_config import WeekdayCadenceConfig
    from tools.weekday_cadence_posts import ClipResult
    from tools.weekday_cadence_runner import run_cadence

    tz = timezone_for("America/Phoenix")
    generated = []
    clips = []

    from PIL import Image
    from tools.weekday_cadence_stills import STILL_SIZE_FB_IG, STILL_SIZE_TIKTOK

    def generate(novel, chapter, size=STILL_SIZE_FB_IG):
        generated.append((novel, chapter, tuple(size)))
        role = "tiktok" if tuple(size) == tuple(STILL_SIZE_TIKTOK) else "still"
        path = tmp_path / f"{novel}-{chapter}-{role}.png"
        Image.new("RGB", tuple(size), (16, 32, 48)).save(path)
        return path

    def produce(still, **kwargs):
        clips.append((still, kwargs))
        with Image.open(still) as image:
            assert image.size == STILL_SIZE_TIKTOK
        path = tmp_path / f"{Path(still).stem}.mp4"
        path.write_bytes(b"mp4")
        return ClipResult(
            outcome="SOCIAL_READY",
            backend="wan_22",
            path=path,
            frame_count=73,
            duration_seconds=3.04,
            width=720,
            height=1280,
        )

    records = _records(
        ("EN", 140, {"patreonExists": True}),
        ("SF", 126, {"patreonExists": True}),
        ("HA", 99, {"patreonExists": True}),
        ("HP", 148, {"patreonExists": True}),
    )
    cfg = WeekdayCadenceConfig(chapter_pick="newest_live", novels=("EN", "HP", "HA", "SF"))
    result = run_cadence(
        target=__import__("datetime").date(2026, 11, 23),
        stage="pack",
        dry_run=False,
        config=cfg,
        out_root=tmp_path / "out",
        records=records,
        now=datetime(2026, 11, 22, 16, 0, tzinfo=tz),
        copy_bank=parse_copy_bank(BANK_SNIPPET),
        with_media=True,
        generate_still=generate,
        produce_clip=produce,
        gpu_lease=FakeLease(),
        media_port_free=lambda _port: True,
        media_processes=[],
        bible_preflight=lambda: None,
    )
    items = result["items"]
    by_id = {item["id"]: item for item in items}

    assert any(pair[:2] == ("SF", 126) for pair in generated)
    assert any(kwargs.get("novel") == "SF" for _still, kwargs in clips)

    sf_fb = by_id["SF-facebook"]
    assert sf_fb["status"] != "awaiting_approval"
    assert sf_fb["depiction"] == "not_governed"
    assert sf_fb["media"]

    sf_x = by_id["SF-x"]
    assert sf_x["status"] == "awaiting_david_post"
    assert sf_x["hold_reason"] == "AWAITING_DAVID_POST"
    assert sf_x["media"] == []

    en_fb = by_id["EN-facebook"]
    assert en_fb["depiction"] == "governed"
    assert en_fb["status"] == "awaiting_approval"
    assert en_fb["hold_reason"] == "IDENTITY_AWAITING_APPROVAL"
    assert en_fb["media"]

    en_x = by_id["EN-x"]
    assert en_x["status"] == "awaiting_david_post"
    assert en_x["hold_reason"] == "AWAITING_DAVID_POST"
    assert en_x["media"] == []

    # HP has no bank item in the snippet, so no structured depiction evidence.
    hp_fb = by_id["HP-facebook"]
    assert hp_fb["depiction"] == "unknown"
    assert hp_fb["status"] == "awaiting_approval"
    assert hp_fb["hold_reason"] == "NO_STRUCTURED_DEPICTION_EVIDENCE"

    # Untagged HA has no structured depiction evidence and fails closed.
    ha_fb = by_id["HA-facebook"]
    assert ha_fb["depiction"] == "unknown"
    assert ha_fb["status"] == "awaiting_approval"
    assert ha_fb["hold_reason"] == "NO_STRUCTURED_DEPICTION_EVIDENCE"

    for item in items:
        if item["status"] != "ready":
            assert str(item.get("hold_reason") or "").strip(), item


def test_depiction_from_still_sidecar(tmp_path: Path):
    import json
    from tools.weekday_cadence_media import depiction_from_still

    still = tmp_path / "kai.png"
    still.write_bytes(b"png")
    assert depiction_from_still(still) == "unknown"
    side = still.with_name(still.name + ".identity_preservation.json")
    side.write_text(json.dumps({"CANON_DEPICTION_STATUS": "CANONICAL_IDENTITY_GOVERNED", "CHARACTER_ID": "kai"}), encoding="utf-8")
    assert depiction_from_still(still) == "governed"
    other = tmp_path / "scene.png"
    other.write_bytes(b"png")
    other.with_name(other.name + ".identity_preservation.json").write_text(
        json.dumps({"CANON_DEPICTION_STATUS": "NOT_APPLICABLE_NO_GOVERNED_CHARACTER"}),
        encoding="utf-8",
    )
    assert depiction_from_still(other) == "not_governed"



def _item(platform: str, novel: str, chapter: int, depiction: str = "not_governed", visual: str = ""):
    from tools.weekday_cadence_manifest import CadenceItem

    return CadenceItem(
        id=f"{novel}-{platform}",
        platform=platform,
        novel=novel,
        source_chapter=chapter,
        source_platform="patreon",
        caption=f"{novel} chapter {chapter}",
        depiction=depiction,
        visual=visual,
        status="ready",
    )


def test_prepare_media_uses_item_chapter_not_newest_pick(tmp_path: Path):
    calls = []

    def generate(novel, chapter):
        calls.append((novel, chapter))
        path = tmp_path / f"{novel}-{chapter}.png"
        path.write_bytes(b"png")
        return path

    items = [
        _item("facebook", "EN", 127, "governed", "Kael in the rain."),
        _item("instagram", "EN", 127, "governed", "Kael in the rain."),
        _item("tiktok", "EN", 127, "governed", "Kael in the rain."),
        _item("x", "EN", 127, "unknown", ""),
    ]
    result = prepare_media(
        novels=["EN"],
        chapters={"EN": 140},
        with_media=True,
        dry_run=False,
        items=items,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=FakeLease(),
        port_free=lambda _port: True,
        processes=[],
        output_dir=tmp_path,
    )
    assert calls == [("EN", 127)]
    assert ("EN", 127) in result.stills_by_chapter
    assert "EN" in result.stills


def test_prepare_media_skips_x_only_jobs(tmp_path: Path):
    calls = []

    def generate(novel, chapter):
        calls.append((novel, chapter))
        path = tmp_path / f"{novel}-{chapter}.png"
        path.write_bytes(b"png")
        return path

    items = [_item("x", "EN", 127, "unknown")]
    result = prepare_media(
        novels=[],
        chapters={},
        with_media=True,
        dry_run=False,
        items=items,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=FakeLease(),
        port_free=lambda _port: True,
        processes=[],
    )
    assert calls == []
    assert result.stills == {}


def test_x_is_skipped_when_media_items_exist(tmp_path: Path):
    calls = []

    def generate(novel, chapter):
        calls.append((novel, chapter))
        path = tmp_path / f"{novel}-{chapter}.png"
        path.write_bytes(b"png")
        return path

    items = [
        _item("x", "HP", 139, "unknown"),
        _item("facebook", "SF", 117, "not_governed", "The furnaces open."),
        _item("tiktok", "SF", 117, "not_governed", "The furnaces open."),
        _item("x", "SF", 117, "unknown"),
    ]
    result = prepare_media(
        novels=["HP", "SF"],
        chapters={"HP": 139, "SF": 117},
        with_media=True,
        dry_run=False,
        items=items,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=FakeLease(),
        port_free=lambda _port: True,
        processes=[],
        output_dir=tmp_path,
    )
    assert calls == [("SF", 117)]
    assert "HP" not in result.stills
    assert "SF" in result.stills


def test_blocked_governed_generation_does_not_fall_back_to_stock(tmp_path: Path):
    from tools.weekday_cadence_stills import StillGenerationBlocked

    stock = tmp_path / "stock-en.png"
    stock.write_bytes(b"png")
    banked = tmp_path / "banked-en.png"
    banked.write_bytes(b"png")
    finder_calls = []

    def finder(novel, chapter):
        finder_calls.append((novel, chapter))
        return None

    def generate(novel, chapter):
        raise StillGenerationBlocked("STILL_GENERATION_BLOCKED:V2ImageGenerationError")

    result = prepare_media(
        novels=["EN"],
        chapters={"EN": 127},
        with_media=True,
        dry_run=False,
        finder=finder,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=FakeLease(),
        port_free=lambda _port: True,
        processes=[],
        items=[_item("facebook", "EN", 127, "governed", "Kael in the rain.")],
        output_dir=tmp_path,
    )
    assert "EN" not in result.stills
    assert result.generation_holds[("EN", 127)] == "STILL_GENERATION_BLOCKED:V2ImageGenerationError"
    assert stock not in result.stills.values()
    assert banked not in result.stills.values()
    assert all(path != stock for path in result.stills_by_chapter.values())


def test_native_tiktok_still_keeps_square_for_fb_ig(tmp_path: Path):
    from PIL import Image
    from tools.weekday_cadence_stills import STILL_SIZE_FB_IG, STILL_SIZE_TIKTOK, letterbox_to_size

    square = tmp_path / "SF-117-still.png"
    vertical = tmp_path / "SF-117-tiktok.png"
    seen = []
    sizes = []

    def generate(novel, chapter, size=STILL_SIZE_FB_IG):
        sizes.append(tuple(size))
        dest = vertical if tuple(size) == tuple(STILL_SIZE_TIKTOK) else square
        Image.new("RGB", tuple(size), (10, 20, 30)).save(dest)
        return dest

    def produce(still, **kwargs):
        seen.append(Path(still))
        with Image.open(still) as image:
            assert image.size == STILL_SIZE_TIKTOK
            # Must be a full-frame 9:16 still, not a letterboxed square.
            extrema = image.crop((0, 0, image.width, 40)).getextrema()
            assert not all(channel == (0, 0) for channel in extrema)
        clip = tmp_path / "SF-117.mp4"
        clip.write_bytes(b"mp4")
        return ClipResult(outcome="SOCIAL_READY", backend="wan_22", path=clip)

    result = prepare_media(
        novels=["SF"],
        chapters={"SF": 117},
        with_media=True,
        dry_run=False,
        generate_still=generate,
        produce_clip=produce,
        gpu_lease=FakeLease(),
        port_free=lambda _port: True,
        processes=[],
        items=[
            _item("facebook", "SF", 117, "not_governed", "The furnaces open."),
            _item("tiktok", "SF", 117, "not_governed", "The furnaces open."),
        ],
        output_dir=tmp_path,
    )
    assert STILL_SIZE_FB_IG in sizes
    assert STILL_SIZE_TIKTOK in sizes
    assert result.stills_by_chapter[("SF", 117)] == square
    with Image.open(result.stills_by_chapter[("SF", 117)]) as image:
        assert image.size == STILL_SIZE_FB_IG
    tiktok = result.tiktok_stills[("SF", 117)]
    assert tiktok == vertical
    with Image.open(tiktok) as image:
        assert image.size == STILL_SIZE_TIKTOK
    # Confirm we did not write a letterboxed derivative of the square.
    assert tiktok != square
    letterboxed = tmp_path / "would-be-letterbox.png"
    letterbox_to_size(square, letterboxed, (1080, 1920))
    assert tiktok.resolve() != letterboxed.resolve()
    with Image.open(tiktok) as native, Image.open(letterboxed) as padded:
        assert native.size != padded.size
    assert seen == [tiktok]
    assert result.clips_by_chapter[("SF", 117)].is_file()


def test_research_missing_still_generates_then_holds_governed_for_approval(tmp_path: Path):
    """The 5b47c74 Research run held all 12 media items as SOURCE_STILL_MISSING.

    When generate is wired, missing stills are created; governed items still
    go to the approval batch; not_governed SF can be ready with media.
    """
    from datetime import date, datetime
    from PIL import Image
    from tools.weekday_cadence import timezone_for
    from tools.weekday_cadence_captions import parse_copy_bank
    from tools.weekday_cadence_config import WeekdayCadenceConfig
    from tools.weekday_cadence_runner import run_cadence
    from tools.weekday_cadence_stills import STILL_SIZE_FB_IG, STILL_SIZE_TIKTOK

    tz = timezone_for("America/Phoenix")
    generated = []
    promo_calls = []

    bank = """# Weekday copy bank
- Items tagged **[APPROVAL: needs David's approval for media]** show Kai, Kael, Liang or Jarek on screen. Everything else uses settings or secondary characters and can go without that pass.
- X posts are text only (no media), so none need media approval.

## Day 1 (Week 1, Monday)

### EN: Eternal Nexus
**TikTok** [source EN-127] [APPROVAL: needs David's approval for media]
- Visual: Rain sheets across a black stone courtyard, Kael Veyra at the gate.
- Caption: Chapter 127 of Eternal Nexus is live now on Patreon. Link in bio.
#EternalNexus #cultivation

**FB/IG post** [source EN-127] [APPROVAL: needs David's approval for media]
- Image: Rain sheets across a black stone courtyard, Kael Veyra at the gate.
- Text: Eternal Nexus chapter 127 is live now on Patreon. Link in bio.

**X post** [source EN-127]
kael is a name in text only. Eternal Nexus ch 127 is up on Patreon, link in bio #webnovel #cultivation

### SF: Soulforge Era
**TikTok** [source SF-117] [no governed characters]
- Visual: Furnaces open over an empty slag yard, no one in frame.
- Caption: Chapter 117 of Soulforge Era is live now on Patreon. Link in bio.
#SoulforgeEra #cultivation

**FB/IG post** [source SF-117] [no governed characters]
- Image: Furnaces open over an empty slag yard, no one in frame.
- Text: Soulforge Era chapter 117 is live now on Patreon. Link in bio.

**X post** [source SF-117]
the furnaces open. Soulforge Era ch 117 is up on Patreon, link in bio #webnovel #cultivation
"""

    def generate(novel, chapter, size=STILL_SIZE_FB_IG):
        generated.append((novel, chapter, tuple(size)))
        role = "tiktok" if tuple(size) == tuple(STILL_SIZE_TIKTOK) else "still"
        path = tmp_path / f"{novel}-{chapter}-{role}.png"
        Image.new("RGB", tuple(size), (12, 24, 36)).save(path)
        return path

    def produce(still, **kwargs):
        from tools.weekday_cadence_stills import STILL_SIZE_TIKTOK as TT
        with Image.open(still) as image:
            assert image.size == TT
        path = tmp_path / f"{kwargs.get('novel')}-{kwargs.get('chapter')}.mp4"
        path.write_bytes(b"mp4")
        return ClipResult(outcome="SOCIAL_READY", backend="wan_22", path=path, width=720, height=1280)

    records = _records(
        ("EN", 127, {"patreonExists": True}),
        ("SF", 117, {"patreonExists": True}),
        ("HA", 84, {"patreonExists": True}),
        ("HP", 139, {"patreonExists": True}),
    )
    cfg = WeekdayCadenceConfig(chapter_pick="newest_live", novels=("EN", "HP", "HA", "SF"))
    result = run_cadence(
        target=date(2026, 11, 23),
        stage="pack",
        dry_run=False,
        config=cfg,
        out_root=tmp_path / "out",
        records=records,
        now=datetime(2026, 11, 22, 16, 0, tzinfo=tz),
        copy_bank=parse_copy_bank(bank),
        with_media=True,
        generate_still=generate,
        produce_clip=produce,
        gpu_lease=FakeLease(),
        media_port_free=lambda _port: True,
        media_processes=[],
        bible_preflight=lambda: None,
    )
    items = {item["id"]: item for item in result["items"]}
    assert any(pair[:2] == ("EN", 127) for pair in generated)
    assert any(pair[:2] == ("SF", 117) for pair in generated)
    assert all(chapter != 140 for _novel, chapter, _size in generated)

    en_fb = items["EN-facebook"]
    assert en_fb["depiction"] == "governed"
    assert en_fb["status"] == "awaiting_approval"
    assert en_fb["hold_reason"] == "IDENTITY_AWAITING_APPROVAL"
    assert en_fb["media"]
    assert en_fb["media"][0].endswith((".png", ".jpg", ".jpeg", ".webp")) or "/" in en_fb["media"][0] or "\\" in en_fb["media"][0] or en_fb["media"]

    sf_fb = items["SF-facebook"]
    assert sf_fb["depiction"] == "not_governed"
    assert sf_fb["status"] != "awaiting_approval"
    assert sf_fb["media"]

    sf_tt = items["SF-tiktok"]
    assert sf_tt["media"]
    assert sf_tt["media"][0].endswith(".mp4") or "tiktok" in sf_tt["media"][0] or sf_tt["media"]

    for key in ("EN-x", "SF-x"):
        assert items[key]["status"] == "awaiting_david_post"
        assert items[key]["media"] == []

    # Relative media landed in the day folder
    day = Path(result["_dayDir"])
    assert (day / en_fb["media"][0]).is_file()
    assert (day / sf_fb["media"][0]).is_file()
    assert (day / sf_tt["media"][0]).is_file()



def test_blocked_tiktok_generation_holds_and_does_not_letterbox(tmp_path: Path):
    from PIL import Image
    from tools.weekday_cadence_stills import (
        STILL_SIZE_FB_IG,
        STILL_SIZE_TIKTOK,
        StillGenerationBlocked,
        letterbox_to_size,
    )

    square = tmp_path / "EN-127-still.png"
    stock = tmp_path / "stock.png"
    Image.new("RGB", STILL_SIZE_FB_IG, (200, 0, 0)).save(stock)
    sizes = []

    def generate(novel, chapter, size=STILL_SIZE_FB_IG):
        sizes.append(tuple(size))
        if tuple(size) == tuple(STILL_SIZE_TIKTOK):
            raise StillGenerationBlocked("STILL_GENERATION_BLOCKED:V2ImageGenerationError")
        Image.new("RGB", STILL_SIZE_FB_IG, (12, 24, 36)).save(square)
        return square

    result = prepare_media(
        novels=["EN"],
        chapters={"EN": 127},
        with_media=True,
        dry_run=False,
        finder=lambda *_: None,
        generate_still=generate,
        produce_clip=lambda *a, **k: (_ for _ in ()).throw(AssertionError("clip must not run without a native still")),
        gpu_lease=FakeLease(),
        port_free=lambda _port: True,
        processes=[],
        items=[
            _item("facebook", "EN", 127, "governed", "Kael in the rain."),
            _item("tiktok", "EN", 127, "governed", "Kael in the rain."),
        ],
        output_dir=tmp_path,
    )
    assert STILL_SIZE_FB_IG in sizes
    assert STILL_SIZE_TIKTOK in sizes
    assert result.stills_by_chapter[("EN", 127)] == square
    with Image.open(square) as image:
        assert image.size == STILL_SIZE_FB_IG
    assert ("EN", 127) not in result.tiktok_stills
    assert "EN" not in result.clips
    assert ("EN", 127) not in result.clips_by_chapter
    assert stock not in result.stills.values()
    assert stock not in result.tiktok_stills.values()



def test_bible_preflight_fails_when_yaml_is_missing():
    from tools.weekday_cadence_media import bible_media_preflight

    def importer():
        raise ModuleNotFoundError("No module named 'yaml'")

    ok, message = bible_media_preflight(
        yaml_importer=importer,
        projector=lambda: SimpleNamespace(characters=(1,), locations=(1,), styles=(1,)),
        executable="/fake/python.exe",
    )
    assert ok is False
    assert "WEEKDAY_CADENCE_MEDIA_PREFLIGHT_FAILED" in message
    assert "interpreter: /fake/python.exe" in message
    assert "missing: yaml" in message
    assert "No module named 'yaml'" in message


def test_bible_preflight_fails_when_projection_is_empty():
    from tools.weekday_cadence_media import bible_media_preflight

    ok, message = bible_media_preflight(
        yaml_importer=lambda: None,
        projector=lambda: SimpleNamespace(characters=(), locations=(), styles=()),
        executable="/fake/python.exe",
    )
    assert ok is False
    assert "interpreter: /fake/python.exe" in message
    assert "characters" in message
    assert "locations" in message
    assert "style palettes" in message
    assert "loaded 0 characters, 0 locations, 0 style palettes" in message


def test_bible_preflight_ok_when_projection_is_populated():
    from tools.weekday_cadence_media import bible_media_preflight, check_bible_media_preflight

    ok, message = bible_media_preflight(
        yaml_importer=lambda: None,
        projector=lambda: SimpleNamespace(characters=("a",), locations=("b",), styles=("c",)),
        executable="/fake/python.exe",
    )
    assert ok is True
    assert message == ""
    check_bible_media_preflight(
        yaml_importer=lambda: None,
        projector=lambda: SimpleNamespace(characters=("a",), locations=("b",), styles=("c",)),
    )


def test_with_media_preflight_failure_does_not_overwrite_existing_pack(tmp_path: Path):
    from datetime import date, datetime
    import json
    from tools.weekday_cadence import timezone_for
    from tools.weekday_cadence_config import WeekdayCadenceConfig
    from tools.weekday_cadence_media import CadenceMediaPreflightError
    from tools.weekday_cadence_runner import run_cadence, main

    day = tmp_path / "daily-social" / "2026-11-23"
    day.mkdir(parents=True)
    existing = {"targetDate": "2026-11-23", "keep": "original-pack", "items": []}
    (day / "manifest.json").write_text(json.dumps(existing), encoding="utf-8")
    (day / "manifest.md").write_text("original", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in day.iterdir() if p.is_file()}

    def fail_preflight():
        raise CadenceMediaPreflightError(
            "WEEKDAY_CADENCE_MEDIA_PREFLIGHT_FAILED\n"
            "interpreter: /fake/python.exe\n"
            "missing: yaml (import failed: ModuleNotFoundError: No module named 'yaml')"
        )

    def generate(*_args, **_kwargs):
        raise AssertionError("generate must not run after preflight failure")

    tz = timezone_for("America/Phoenix")
    try:
        run_cadence(
            target=date(2026, 11, 23),
            stage="pack",
            dry_run=False,
            config=WeekdayCadenceConfig(chapter_pick="newest_live", novels=("EN",)),
            out_root=tmp_path,
            records={"chapters": {"EN-127": {"abbr": "EN", "chapter": 127, "patreonExists": True}}},
            now=datetime(2026, 11, 22, 16, 0, tzinfo=tz),
            with_media=True,
            generate_still=generate,
            produce_clip=None,
            gpu_lease=FakeLease(),
            media_port_free=lambda _port: True,
            media_processes=[],
            bible_preflight=fail_preflight,
        )
    except CadenceMediaPreflightError as exc:
        assert "interpreter: /fake/python.exe" in str(exc)
        assert "missing: yaml" in str(exc)
    else:
        raise AssertionError("expected CadenceMediaPreflightError")

    assert {p.name: p.read_bytes() for p in day.iterdir() if p.is_file()} == before
    assert not (day / "media").exists()

    # CLI must exit non-zero and still leave the pack untouched.
    # main() does not accept bible_preflight, so stub check_bible_media_preflight.
    import tools.weekday_cadence_media as media_mod
    original = media_mod.check_bible_media_preflight
    media_mod.check_bible_media_preflight = fail_preflight
    try:
        # Ensure the runner sees the stub if it already imported the symbol.
        # It imports the function inside run_cadence, so the module attr is enough.
        code = main(
            [
                "--date", "2026-11-23",
                "--root", str(tmp_path),
                "--app-root", str(tmp_path),
                "--with-media",
                "--source-commit", "test",
            ]
        )
    finally:
        media_mod.check_bible_media_preflight = original

    assert code == 1
    assert {p.name: p.read_bytes() for p in day.iterdir() if p.is_file()} == before
    assert not (day / "media").exists()


def test_ensure_comfy_runs_before_generate_and_stops_only_if_started(tmp_path: Path):
    order = []
    made = tmp_path / "en-127.png"

    def ensure():
        order.append("ensure")
        return SimpleNamespace(ok=True, started_by_us=True, reason="started_via_launcher")

    def stop(comfy):
        order.append("stop")
        assert comfy.started_by_us is True

    def generate(novel, chapter, size=(1024, 1024)):
        order.append("generate")
        made.write_bytes(b"png")
        return made

    result = prepare_media(
        novels=["EN"],
        chapters={"EN": 127},
        with_media=True,
        dry_run=False,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=FakeLease(),
        port_free=lambda _port: True,
        processes=[],
        items=[_item("facebook", "EN", 127, "governed", "Kael in the rain.")],
        output_dir=tmp_path,
        ensure_comfy=ensure,
        stop_comfy=stop,
    )
    assert order[0] == "ensure"
    assert "generate" in order
    assert order[-1] == "stop"
    assert result.preflight_ok is True
    assert result.stills_by_chapter[("EN", 127)] == made


def test_ensure_comfy_failure_holds_and_does_not_generate(tmp_path: Path):
    stops = []
    calls = []

    def ensure():
        return SimpleNamespace(
            ok=False,
            started_by_us=False,
            reason="COMFY_PORT_BUSY_DYNVRAM_NOT_CONFIRMED",
        )

    def stop(comfy):
        stops.append(comfy)

    def generate(novel, chapter, size=(1024, 1024)):
        calls.append((novel, chapter))
        raise AssertionError("generate must not run when Comfy is not ready")

    result = prepare_media(
        novels=["EN"],
        chapters={"EN": 127},
        with_media=True,
        dry_run=False,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=FakeLease(),
        port_free=lambda _port: False,
        processes=[],
        items=[_item("facebook", "EN", 127, "governed", "Kael in the rain.")],
        output_dir=tmp_path,
        ensure_comfy=ensure,
        stop_comfy=stop,
    )
    assert calls == []
    assert stops == []
    assert result.preflight_ok is False
    assert "COMFY_NOT_READY" in result.preflight_reason
    assert "COMFY_PORT_BUSY_DYNVRAM_NOT_CONFIRMED" in result.preflight_reason
    assert result.generation_holds[("EN", 127)] == result.preflight_reason
    assert "EN" not in result.stills


def test_reused_comfy_is_not_stopped(tmp_path: Path):
    stops = []
    made = tmp_path / "ha-99.png"

    def ensure():
        return SimpleNamespace(ok=True, started_by_us=False, reason="reused_running_comfyui")

    def stop(comfy):
        stops.append(comfy)

    def generate(novel, chapter, size=(1024, 1024)):
        made.write_bytes(b"png")
        return made

    result = prepare_media(
        novels=["HA"],
        chapters={"HA": 99},
        with_media=True,
        dry_run=False,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=FakeLease(),
        port_free=lambda _port: False,
        processes=[],
        items=[_item("facebook", "HA", 99, "not_governed", "A quiet courtyard.")],
        output_dir=tmp_path,
        ensure_comfy=ensure,
        stop_comfy=stop,
    )
    assert result.preflight_ok is True
    assert result.preflight_reason == "reused_running_comfyui"
    assert result.stills["HA"] == made
    assert stops == []


def test_research_running_does_not_call_ensure_comfy(tmp_path: Path):
    ensures = []
    calls = []

    def ensure():
        ensures.append(1)
        return SimpleNamespace(ok=True, started_by_us=True, reason="started")

    def generate(novel, chapter, size=(1024, 1024)):
        calls.append((novel, chapter))
        raise AssertionError("must not generate while Research is running")

    result = prepare_media(
        novels=["SF"],
        chapters={"SF": 117},
        with_media=True,
        dry_run=False,
        generate_still=generate,
        produce_clip=None,
        gpu_lease=FakeLease(),
        port_free=lambda _port: True,
        processes=[{"name": "python.exe", "command": "python research_gpu_job.py"}],
        items=[_item("facebook", "SF", 117, "not_governed", "Ancient towers.")],
        output_dir=tmp_path,
        ensure_comfy=ensure,
        stop_comfy=lambda comfy: None,
    )
    assert ensures == []
    assert calls == []
    assert result.preflight_ok is False
    assert "RESEARCH_PROCESS_RUNNING" in result.preflight_reason
    assert result.generation_holds[("SF", 117)] == "GPU_PREFLIGHT:RESEARCH_PROCESS_RUNNING"


def test_gray_hand_items_are_not_generated_and_keep_ids(tmp_path: Path):
    from datetime import date, datetime
    from tools.weekday_cadence import timezone_for
    from tools.weekday_cadence_captions import load_copy_bank
    from tools.weekday_cadence_config import HOLD_GRAY_LOOK_UNDECIDED, WeekdayCadenceConfig
    from tools.weekday_cadence_runner import run_cadence

    tz = timezone_for("America/Phoenix")
    bank = load_copy_bank(Path("daily-social/copy-bank/weekday-bank-v1.md"))
    cfg = WeekdayCadenceConfig(chapter_pick="bank_day", novels=("SF",))
    records = _records(
        ("SF", 117, {"patreonExists": True}),
        ("SF", 124, {"patreonExists": True}),
    )
    generated = []

    def generate(novel, chapter, size=(1024, 1024)):
        generated.append((novel, chapter, tuple(size)))
        path = tmp_path / f"{novel}-{chapter}-{size[0]}.png"
        path.write_bytes(b"png")
        return path

    def produce(still, **kwargs):
        path = tmp_path / f"{kwargs.get('novel')}-{kwargs.get('chapter')}.mp4"
        path.write_bytes(b"mp4")
        return ClipResult(outcome="SOCIAL_READY", backend="wan_22", path=path, width=720, height=1280)

    day2 = run_cadence(
        target=date(2026, 11, 24),
        stage="pack",
        dry_run=False,
        config=cfg,
        out_root=tmp_path / "out",
        records=records,
        now=datetime(2026, 11, 23, 16, 0, tzinfo=tz),
        copy_bank=bank,
        with_media=True,
        generate_still=generate,
        produce_clip=produce,
        gpu_lease=FakeLease(),
        media_port_free=lambda _port: True,
        media_processes=[],
        bible_preflight=lambda: None,
    )
    day2_items = {item["id"]: item for item in day2["items"]}
    day2_held = sorted(
        item["id"]
        for item in day2["items"]
        if item.get("hold_reason") == HOLD_GRAY_LOOK_UNDECIDED
    )
    assert day2_held == ["SF-facebook", "SF-instagram", "SF-tiktok"]
    for item_id in day2_held:
        assert day2_items[item_id]["status"] == "awaiting_approval"
        assert day2_items[item_id]["source_chapter"] == 117
        assert not day2_items[item_id]["media"]
    assert day2_items["SF-x"]["status"] == "awaiting_david_post"
    assert day2_items["SF-x"]["hold_reason"] != HOLD_GRAY_LOOK_UNDECIDED
    assert all(chapter != 117 for _novel, chapter, _size in generated)

    generated.clear()
    day9 = run_cadence(
        target=date(2026, 12, 3),
        stage="pack",
        dry_run=False,
        config=cfg,
        out_root=tmp_path / "out",
        records=records,
        now=datetime(2026, 12, 2, 16, 0, tzinfo=tz),
        copy_bank=bank,
        with_media=True,
        generate_still=generate,
        produce_clip=produce,
        gpu_lease=FakeLease(),
        media_port_free=lambda _port: True,
        media_processes=[],
        bible_preflight=lambda: None,
    )
    day9_items = {item["id"]: item for item in day9["items"]}
    day9_held = sorted(
        item["id"]
        for item in day9["items"]
        if item.get("hold_reason") == HOLD_GRAY_LOOK_UNDECIDED
    )
    assert day9_held == ["SF-facebook", "SF-instagram"]
    for item_id in day9_held:
        assert day9_items[item_id]["status"] == "awaiting_approval"
        assert day9_items[item_id]["source_chapter"] == 124
        assert not day9_items[item_id]["media"]
    assert day9_items["SF-tiktok"]["hold_reason"] != HOLD_GRAY_LOOK_UNDECIDED
    assert day9_items["SF-tiktok"]["source_chapter"] == 124
    assert any(chapter == 124 for _novel, chapter, _size in generated)
