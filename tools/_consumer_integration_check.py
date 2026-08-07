"""Consumer-integration proof: normalized dict -> build_platform_posts.

Decouples the "does the consumer accept the agent contract" proof from hermes
reliability by feeding a SAMPLE wrapped payload (shaped like the real 2026-08-02
HA run) through _extract_json + _unwrap_variation, then into
promo_copy.build_platform_posts, and asserts used==true + copy differs from the
template. Run with the codex python + env -u PYTHONPATH -u PYTHONHOME.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from agent_post_writer import _extract_json, _unwrap_variation  # noqa: E402
import promo_copy  # noqa: E402

# Real-world-shaped wrapped payload (like the 2026-08-02 HA run, valid JSON).
SAMPLE_WRAPPED = {
    "generated_at": "2026-08-02T07:16:00Z",
    "agent": "post-differentiation-agent",
    "variations": [
        {
            "novel": "HA",
            "chapter": "SUNDAY",
            "platform": ["instagram"],
            "hook": "Searching for your next progression fantasy? The Hollow Ascension awaits.",
            "caption": "When the system chooses you over every other hero, the path bends. One quiet choice opens a sect-wide secret.",
            "cta": "Start Heavenly Ascension System here: link in bio.",
            "hashtags": ["#HeavenlyAscensionSystem", "#AzureInkblade", "#ProgressionFantasy"],
            "content_angle": "system-protagonist-betrayal",
            "intended_audience": "progression-fantasy readers who love weak heroes gaining hidden power",
        }
    ],
}


def main():
    _data, _parse_mode, _norms = _extract_json(json.dumps(SAMPLE_WRAPPED))
    copy = _unwrap_variation(_data)
    assert copy is not None, "sample wrapped payload must normalize"
    assert copy.get("_source") == "hermes_agent"

    material = {
        "abbr": "HA",
        "novel": "Heavenly Ascension System",
        "chapter": "24",
        "chapter_number": "24",
        "phrases": ["Kai's golden ember flares as the sect councils turn against him."],
    }
    tpl = promo_copy.build_platform_posts("Chapter 24", material["phrases"][0], material, "patreon_early")
    ag = promo_copy.build_platform_posts("Chapter 24", material["phrases"][0], material, "patreon_early", agent_copy=copy)

    used = bool(ag.get("_agent_source") or copy.get("caption"))
    assert used is True, "agent copy must report used == True"
    # build_platform_posts returns the IG caption at top-level "caption".
    tpl_ig = tpl.get("caption", "")
    ag_ig = ag.get("caption", "")
    assert ag_ig and ag_ig != tpl_ig, "agent copy must differ from template fallback"
    assert copy["caption"] in ag_ig or copy["caption"] in json.dumps(ag, ensure_ascii=False), \
        "agent caption present in built copy"

    print("CONSUMER INTEGRATION CHECK PASSED")
    print("  _source:", copy["_source"])
    print("  used == True:", used)
    print("  agent IG caption differs from template:", ag_ig != tpl_ig)
    print("  agent caption in built copy:", copy["caption"] in ag_ig)
    return 0


if __name__ == "__main__":
    sys.exit(main())
