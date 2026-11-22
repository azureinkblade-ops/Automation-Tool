"""--with-media planning uses stubs only; never starts ComfyUI, ffmpeg, or a lease on a busy GPU."""

from __future__ import annotations

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
    still = tmp_path / "en.png"
    still.write_bytes(b"png")
    clip_path = tmp_path / "en.mp4"
    clip_path.write_bytes(b"mp4")
    lease = FakeLease()

    def produce(path, **_kwargs):
        assert path == still
        return ClipResult(outcome="SOCIAL_READY", backend="wan_22", path=clip_path)

    result = prepare_media(
        novels=["EN"],
        chapters={"EN": 140},
        with_media=True,
        dry_run=False,
        existing_stills={"EN": still},
        produce_clip=produce,
        gpu_lease=lease,
        port_free=lambda _port: True,
        processes=[],
    )
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

    def generate(novel, chapter):
        generated.append((novel, chapter))
        path = tmp_path / f"{novel}-{chapter}.png"
        path.write_bytes(b"png")
        return path

    def produce(still, **kwargs):
        clips.append((still, kwargs))
        path = tmp_path / f"{Path(still).stem}.mp4"
        path.write_bytes(b"mp4")
        return ClipResult(
            outcome="SOCIAL_READY",
            backend="wan_22",
            path=path,
            frame_count=73,
            duration_seconds=3.04,
            width=1080,
            height=1920,
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
    )
    items = result["items"]
    by_id = {item["id"]: item for item in items}

    assert ("SF", 126) in generated
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

    # Convention-untagged HA is not_governed and should get media.
    ha_fb = by_id["HA-facebook"]
    assert ha_fb["depiction"] == "not_governed"
    assert ha_fb["status"] != "awaiting_approval"
    assert ha_fb["media"]

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
