"""Facebook hashtag cap regressions without weakening differentiated copy."""

from __future__ import annotations

import re

import promo_copy


def _hashtags(text: str) -> list[str]:
    return re.findall(r"#\w+", text or "")


def test_facebook_public_copy_keeps_first_five_unique_hashtags():
    source = "Body\n\n#One #Two #Three #Two #Four #Five #Six #Seven"

    result = promo_copy.public_copy_without_links(source, "facebook")

    assert _hashtags(result) == ["#One", "#Two", "#Three", "#Four", "#Five"]


def test_facebook_fallback_rotates_but_never_exceeds_five():
    monday = promo_copy.fallback_social_copy("Eternal Nexus", "EN", "Monday", "chapter-12")
    tuesday = promo_copy.fallback_social_copy("Eternal Nexus", "EN", "Tuesday", "chapter-12")
    monday_tags = _hashtags(monday["facebook"])
    tuesday_tags = _hashtags(tuesday["facebook"])

    assert len(monday_tags) == 5
    assert len(tuesday_tags) == 5
    assert monday_tags != tuesday_tags


def test_agent_differentiation_survives_facebook_hashtag_cap():
    distinctive_caption = "Kael discovers the system has been writing his choices ahead of him."
    agent_copy = {
        "hook": "The rain knows his name.",
        "caption": distinctive_caption,
        "cta": "Start Eternal Nexus.",
        "hashtags": [f"#AgentTag{index}" for index in range(1, 9)],
        "content_angle": "system betrayal",
        "intended_audience": "progression fantasy readers",
    }
    posts = promo_copy.build_platform_posts(
        "Chapter 12: Neon Rain",
        "Kael stands in neon rain while the system changes the rules.",
        {"abbr": "EN", "novel": "Eternal Nexus", "chapter": "12", "phrases": []},
        agent_copy=agent_copy,
    )

    assert distinctive_caption in posts["facebook_post"]
    assert distinctive_caption in posts["caption"]
    assert len(_hashtags(posts["facebook_post"])) <= 5
    assert len(_hashtags(posts["caption"])) > 5
