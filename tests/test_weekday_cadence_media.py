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
    assert result.identity_needed["EN"] is True
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
    assert result.identity_needed["HA"] is True
    assert result.plans[0].identity_character == "Kai"


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
