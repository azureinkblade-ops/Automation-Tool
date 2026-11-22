"""Optional Writer copy bank and Facebook/Instagram hashtag attachment."""

from __future__ import annotations

from tools.weekday_cadence_captions import (
    HASHTAG_SOURCE_PROMO_COPY,
    HASHTAG_SOURCE_WRITER_BANK,
    append_hashtags,
    apply_platform_hashtags,
    captions_for_novel,
    extract_hashtags,
    novel_hashtag_set,
    parse_copy_bank,
    sanitize_caption_for_tiers,
    select_bank_caption,
)

SAMPLE_BANK = """
# Weekday copy bank (fixture)

## Day 1 (Week 1, Monday)

### EN: Eternal Nexus
**TikTok** [source EN-138]
- Caption: Bank tiktok for EN 138 is live now on Patreon. Link in bio.
#EternalNexus #cultivation

**FB/IG post** [source EN-138]
- Text: Bank facebook and instagram prose for chapter 138 is live now on Patreon. Link in bio.

**X post** [source EN-138]
bank x line for ch 138 is up on Patreon, link in bio #webnovel #cultivation

**FB/IG post** [source EN-137]
- Text: Older chapter must not be used when the picker allowed 138.

## Day 2 (Week 1, Tuesday)

### EN: Eternal Nexus
**FB/IG post** [source EN-138]
- Text: Tuesday variant of EN 138 should win when the target weekday is Tuesday.
"""


def test_parse_and_select_matching_chapter_only():
    items = parse_copy_bank(SAMPLE_BANK)
    assert len(items) == 5
    monday = select_bank_caption(
        items, novel="EN", chapter=138, platform="facebook", weekday="Monday", allowed_chapters=[138]
    )
    assert monday is not None
    assert "Bank facebook and instagram" in monday.text
    tuesday = select_bank_caption(
        items, novel="EN", chapter=138, platform="instagram", weekday="Tuesday", allowed_chapters=[138]
    )
    assert tuesday is not None
    assert "Tuesday variant" in tuesday.text
    # Picker allowed 138: the EN-137 bank item is rejected.
    older = select_bank_caption(
        items, novel="EN", chapter=137, platform="facebook", weekday="Monday", allowed_chapters=[138]
    )
    assert older is None
    missing = select_bank_caption(
        items, novel="EN", chapter=140, platform="facebook", allowed_chapters=[140]
    )
    assert missing is None


def test_fallback_when_bank_has_no_match():
    items = parse_copy_bank(SAMPLE_BANK)
    caps = captions_for_novel(
        novel="EN",
        chapter=140,
        source_platform="patreon",
        weekday="Monday",
        bank=items,
        allowed_chapters=[140],
        fallback={"facebook": "Generated facebook copy.", "instagram": "Generated instagram copy.", "x": "generated x", "tiktok": "generated tt"},
    )
    assert caps["facebook"].startswith("Generated facebook copy.")
    assert caps["x"] == "generated x"


def test_hashtags_added_to_facebook_and_instagram_not_x(monkeypatch):
    tags = ["#AzureInkblade", "#EternalNexus", "#BookTok", "#WebNovel", "#ProgressionFantasy", "#FantasyReads"]

    def fake_set(novel: str):
        assert novel == "EN"
        return tags, HASHTAG_SOURCE_PROMO_COPY

    monkeypatch.setattr("tools.weekday_cadence_captions.novel_hashtag_set", fake_set)
    fb, source = apply_platform_hashtags("A scene is live now on Patreon. Link in bio.", novel="EN", platform="facebook")
    ig, ig_source = apply_platform_hashtags("A scene is live now on Patreon. Link in bio.", novel="EN", platform="instagram")
    x, x_source = apply_platform_hashtags("a short x line #webnovel", novel="EN", platform="x")
    assert source == HASHTAG_SOURCE_PROMO_COPY
    assert ig_source == HASHTAG_SOURCE_PROMO_COPY
    assert x_source is None
    assert extract_hashtags(fb) == tags[:5]  # Facebook cap of 5
    assert extract_hashtags(ig) == tags
    assert extract_hashtags(x) == ["#webnovel"]
    assert "#EternalNexus" not in x


def test_does_not_duplicate_existing_hashtags():
    caption = "A hook. #EternalNexus #AzureInkblade"
    out = append_hashtags(caption, ["#AzureInkblade", "#EternalNexus", "#WebNovel"], limit=5)
    tags = extract_hashtags(out)
    assert tags.count("#AzureInkblade") == 1
    assert tags.count("#EternalNexus") == 1
    assert "#WebNovel" in tags


def test_hashtag_source_prefers_promo_copy_when_available():
    tags, source = novel_hashtag_set("EN")
    # In the worktree / repo this is promo_copy.social_profile. If promo_copy
    # cannot be imported (isolated box), the Writer bank list is the fallback.
    assert source in {HASHTAG_SOURCE_PROMO_COPY, HASHTAG_SOURCE_WRITER_BANK}
    assert tags
    if source == HASHTAG_SOURCE_PROMO_COPY:
        assert "#EternalNexus" in tags or "#AzureInkblade" in tags


def test_partial_live_caption_does_not_name_a_tier():
    text = (
        "Eternal Nexus chapter 140 is live now on Patreon for Inner Disciple and Path Initiate. "
        "Link in bio."
    )
    cleaned = sanitize_caption_for_tiers(text, ["Inner Disciple"])
    assert "Inner Disciple" not in cleaned
    assert "Path Initiate" not in cleaned
    assert "Patreon" in cleaned
    # Both tiers live: leave names alone.
    both = sanitize_caption_for_tiers(text, ["Inner Disciple", "Path Initiate"])
    assert "Inner Disciple" in both and "Path Initiate" in both


def test_captions_for_novel_strips_tiers_when_partial():
    caps = captions_for_novel(
        novel="EN",
        chapter=140,
        source_platform="patreon",
        weekday="Monday",
        bank=[],
        allowed_chapters=[140],
        fallback={
            "facebook": "EN Ch. 140 is live on Patreon for Path Initiate.",
            "instagram": "EN Ch. 140 is live on Patreon for Path Initiate.",
            "x": "EN Ch. 140 is live on Patreon for Path Initiate.",
            "tiktok": "EN Ch. 140 is live on Patreon for Path Initiate.",
        },
        live_tiers=["Inner Disciple"],
    )
    for platform, text in caps.items():
        assert "Path Initiate" not in text, platform
        assert "Inner Disciple" not in text, platform
        assert "Patreon" in text

def test_exact_chapter_match_never_selects_neighbor_item():
    """EN-140 copy must never land on an EN-139 bank item, even if both are present."""
    bank = """
### EN: Eternal Nexus
**TikTok** [source EN-139]
- Caption: EN-139 tiktok must not be selected for chapter 140.
**FB/IG post** [source EN-139]
- Text: EN-139 facebook must not be selected for chapter 140.
**X post** [source EN-139]
en 139 x must not be selected for chapter 140
**TikTok** [source EN-140]
- Caption: EN-140 tiktok is the only valid tiktok for this pick.
**FB/IG post** [source EN-140]
- Text: EN-140 facebook is the only valid static copy for this pick.
**X post** [source EN-140]
en 140 x is the only valid x copy for this pick
"""
    items = parse_copy_bank(bank)
    assert {(item.chapter, item.kind) for item in items} == {
        (139, "TikTok"),
        (139, "FB/IG post"),
        (139, "X post"),
        (140, "TikTok"),
        (140, "FB/IG post"),
        (140, "X post"),
    }
    for platform in ("facebook", "instagram", "x", "tiktok"):
        # Even if 139 is also in the allowed set, the requested chapter must match exactly.
        picked = select_bank_caption(
            items,
            novel="EN",
            chapter=140,
            platform=platform,
            allowed_chapters=[139, 140],
        )
        assert picked is not None, platform
        assert picked.chapter == 140, platform
        assert "EN-139" not in picked.text
        assert "chapter 139" not in picked.text
        assert "ch 139" not in picked.text
        assert "139" not in picked.text
        assert "140" in picked.text



def test_bank_depiction_markers_are_per_item_not_per_novel():
    from tools.weekday_cadence_captions import parse_copy_bank, load_copy_bank
    from pathlib import Path

    snippet = '''# Weekday copy bank
- Items tagged **[APPROVAL: needs David's approval for media]** show Kai, Kael, Liang or Jarek on screen.

## Day 1 (Week 1, Monday)
**FB/IG post** [source EN-140] [APPROVAL: needs David's approval for media]
- Text: Kael in the rain.

**FB/IG post** [source SF-126] [no governed characters]
- Text: Furnaces only.

**FB/IG post** [source HA-99]
- Text: A door, no approval tag.
'''
    items = {(row.novel, row.chapter, row.kind): row for row in parse_copy_bank(snippet)}
    assert items[("EN", 140, "FB/IG post")].depiction == "governed"
    assert items[("EN", 140, "FB/IG post")].needs_approval is True
    assert items[("SF", 126, "FB/IG post")].depiction == "not_governed"
    assert items[("HA", 99, "FB/IG post")].depiction == "not_governed"

    bank_path = Path("daily-social/copy-bank/weekday-bank-v1.md")
    if bank_path.is_file():
        real = load_copy_bank(bank_path)
        en128 = next(row for row in real if row.novel == "EN" and row.chapter == 128 and row.kind == "FB/IG post")
        assert en128.depiction == "governed"
        sf126 = next(row for row in real if row.novel == "SF" and row.chapter == 126 and row.kind == "FB/IG post")
        assert sf126.depiction == "not_governed"
        en127 = next(row for row in real if row.novel == "EN" and row.chapter == 127 and row.kind == "FB/IG post")
        assert en127.depiction == "not_governed"
        # The Day 1 SF X post sits just above Reel 1's APPROVAL heading and must not inherit it.
        sf117_x = next(row for row in real if row.novel == "SF" and row.chapter == 117 and row.kind == "X post")
        assert sf117_x.depiction == "not_governed"
        assert sf117_x.needs_approval is False
