"""Stubs only: cadence stills use generate_promo_image_v2 and never hit a GPU."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from tools.weekday_cadence_config import DEPICTION_GOVERNED, DEPICTION_NOT_GOVERNED, DEPICTION_UNKNOWN
from tools.weekday_cadence_stills import (
    STILL_SIZE_FB_IG,
    STILL_SIZE_TIKTOK,
    STILL_STYLE,
    StillGenerationBlocked,
    build_still_prompt,
    generate_cadence_still,
    letterbox_to_size,
    structured_image_intent,
)


def _write_png(path: Path, size: tuple[int, int] = STILL_SIZE_FB_IG, color=(20, 40, 80)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def test_sizes_match_existing_conventions():
    assert STILL_SIZE_FB_IG == (1024, 1024)
    assert STILL_SIZE_TIKTOK == (1080, 1920)
    assert STILL_STYLE == "main-posts"


def test_prompt_uses_visual_and_chapter_not_depiction_wording():
    prompt = build_still_prompt(
        novel="EN",
        chapter=127,
        visual="Rain sheets across a black stone courtyard.",
        title="The Gate Opens",
    )
    lowered = prompt.lower()
    assert "Rain sheets across a black stone courtyard." in prompt
    assert "Eternal Nexus chapter 127" in prompt
    assert "The Gate Opens" in prompt
    for banned in (
        "governed",
        "not_governed",
        "approval",
        "identity",
        "depiction",
        "background_only",
        "environment_only",
        "[approval",
        "no governed characters",
    ):
        assert banned not in lowered


def test_structured_intent_is_context_not_prompt():
    governed = structured_image_intent(
        depiction=DEPICTION_GOVERNED,
        novel="EN",
        visual="Kael Veyra stands in the rain.",
        caption="Kael stands in the rain.",
    )
    assert governed is not None
    assert "weekday_cadence_bank" in {getattr(governed, "origin", None), (governed or {}).get("origin") if isinstance(governed, dict) else getattr(governed, "origin", "")}
    chars = getattr(governed, "depicted_characters", None)
    if chars is None and isinstance(governed, dict):
        chars = governed.get("depicted_characters")
    assert chars

    clean = structured_image_intent(
        depiction=DEPICTION_NOT_GOVERNED,
        novel="SF",
        visual="The furnaces open over an empty yard.",
        caption="The furnaces open.",
    )
    assert getattr(clean, "background_only", None) is True or (isinstance(clean, dict) and clean.get("background_only") is True)
    assert getattr(clean, "requested_asset_type", None) == "ENVIRONMENT_ONLY" or (
        isinstance(clean, dict) and clean.get("requested_asset_type") == "ENVIRONMENT_ONLY"
    )
    empty = getattr(clean, "depicted_characters", None)
    if empty is None and isinstance(clean, dict):
        empty = clean.get("depicted_characters")
    assert tuple(empty or ()) == ()

    assert structured_image_intent(depiction=DEPICTION_UNKNOWN, novel="HA") is None


def test_generate_calls_promo_v2_with_intent_and_writes_target(tmp_path: Path):
    calls = []
    target = tmp_path / "EN-127-still.png"

    def generate_promo(style, prompt, dest, **kwargs):
        calls.append((style, prompt, Path(dest), kwargs))
        _write_png(Path(dest))
        return "v2:main-posts"

    path = generate_cadence_still(
        "EN",
        127,
        target=target,
        visual="Rain sheets across a black stone courtyard.",
        depiction=DEPICTION_GOVERNED,
        caption="Kael stands in the rain.",
        chapter_loader=lambda *_: {"title": "The Gate Opens", "text": "unused"},
        generate_promo=generate_promo,
    )
    assert path == target
    assert target.is_file()
    assert Image.open(target).size == STILL_SIZE_FB_IG
    assert len(calls) == 1
    style, prompt, dest, kwargs = calls[0]
    assert style == "main-posts"
    assert dest == target
    assert "Rain sheets across a black stone courtyard." in prompt
    assert "Eternal Nexus chapter 127" in prompt
    lowered = prompt.lower()
    for banned in ("governed", "approval", "not_governed", "depiction", "identity"):
        assert banned not in lowered
    assert kwargs["abbr"] == "EN"
    assert kwargs["chapter"] == 127
    assert kwargs["image_intent"] is not None
    intent = kwargs["image_intent"]
    chars = getattr(intent, "depicted_characters", None) or getattr(intent, "get", lambda *_: None)("depicted_characters")
    if callable(getattr(intent, "get", None)):
        chars = intent.get("depicted_characters")
    else:
        chars = intent.depicted_characters
    assert chars


def test_unknown_depiction_does_not_call_pipeline(tmp_path: Path):
    def generate_promo(*_args, **_kwargs):
        raise AssertionError("unknown depiction must not reach the pipeline")

    try:
        generate_cadence_still(
            "HA",
            84,
            target=tmp_path / "ha.png",
            visual="A door widens by a hair.",
            depiction=DEPICTION_UNKNOWN,
            generate_promo=generate_promo,
            chapter_loader=lambda *_: {"title": "", "text": ""},
        )
    except StillGenerationBlocked as exc:
        assert "NO_STRUCTURED_DEPICTION_EVIDENCE" in str(exc)
    else:
        raise AssertionError("expected StillGenerationBlocked")


def test_blocked_pipeline_does_not_return_stock(tmp_path: Path):
    stock = tmp_path / "stock.png"
    _write_png(stock, color=(200, 0, 0))
    banked = tmp_path / "banked.png"
    _write_png(banked, color=(0, 200, 0))

    def generate_promo(*_args, **_kwargs):
        raise RuntimeError("V2ImageGenerationError: identity blocked")

    try:
        generate_cadence_still(
            "EN",
            127,
            target=tmp_path / "out.png",
            visual="Kael in the rain.",
            depiction=DEPICTION_GOVERNED,
            generate_promo=generate_promo,
            chapter_loader=lambda *_: {"title": "", "text": ""},
        )
    except StillGenerationBlocked as exc:
        assert "STILL_GENERATION_BLOCKED" in str(exc)
    else:
        raise AssertionError("expected StillGenerationBlocked")
    assert not (tmp_path / "out.png").exists()


def test_letterbox_tiktok_is_1080x1920(tmp_path: Path):
    source = _write_png(tmp_path / "square.png", STILL_SIZE_FB_IG)
    dest = tmp_path / "tiktok.png"
    out = letterbox_to_size(source, dest, STILL_SIZE_TIKTOK)
    assert out == dest
    with Image.open(dest) as image:
        assert image.size == STILL_SIZE_TIKTOK
