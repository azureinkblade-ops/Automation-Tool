"""Focused tests for the post-differentiation contract normalization.

Exercises the pure normalization path (_extract_json + _unwrap_variation) without
shelling out to hermes. The controlled end-to-end hermes invocation is run
separately via `python tools/agent_post_writer.py <abbr> <title> <hook>`.

Run: env -u PYTHONPATH -u PYTHONHOME <codex-python> tools/test_agent_post_writer_contract.py
"""

import json
import sys
from pathlib import Path

# Make the repo root importable so `import tools.agent_post_writer` works.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from agent_post_writer import _extract_json, _unwrap_variation  # noqa: E402


FLAT = {
    "hook": "A hook line.",
    "caption": "Caption body.",
    "cta": "Read now.",
    "hashtags": ["#AzureInkblade", "#HeavenlyAscensionSystem"],
    "content_angle": "character-moment",
    "intended_audience": "progression-fantasy readers",
}

WRAPPED = {
    "generated_at": "2026-08-05T14:37",
    "agent": "post-differentiation-agent",
    "variations": [
        {
            "novel": "HA",
            "chapter": "HA-34",
            "platform": "instagram",
            "hook": "Wrapped hook line.",
            "caption": "Wrapped caption body.",
            "cta": "Wrapped CTA.",
            "hashtags": ["#AzureInkblade", "#HeavenlyAscensionSystem", "#ProgressionFantasy"],
            "content_angle": "moral-stakes-reveal",
            "intended_audience": "readers who fear when secrets cost lives.",
        }
    ],
}


def _assert(cond, msg):
    if cond:
        print(f"  PASS: {msg}")
        return True
    print(f"  FAIL: {msg}")
    _assert.failed += 1
    return False


_assert.failed = 0


def test_1_wrapped_normalizes():
    print("[1] wrapped response normalizes to flat contract")
    out = _unwrap_variation(WRAPPED)
    ok = True
    ok &= _assert(isinstance(out, dict), "returns a dict")
    ok &= _assert(out["caption"] == "Wrapped caption body.", "caption unwrapped from variations[0]")
    ok &= _assert(out["hook"] == "Wrapped hook line.", "hook unwrapped")
    ok &= _assert(out["cta"] == "Wrapped CTA.", "cta unwrapped")
    ok &= _assert(out["content_angle"] == "moral-stakes-reveal", "content_angle unwrapped")
    ok &= _assert(out["intended_audience"] == "readers who fear when secrets cost lives.", "intended_audience unwrapped")
    ok &= _assert(out["hashtags"] == ["#AzureInkblade", "#HeavenlyAscensionSystem", "#ProgressionFantasy"], "hashtags unwrapped as list")
    ok &= _assert(out["_source"] == "hermes_agent", "_source identifies agent path")
    return ok


def test_2_flat_legacy_works():
    print("[2] flat legacy response still works")
    out = _unwrap_variation(FLAT)
    ok = True
    ok &= _assert(isinstance(out, dict), "returns a dict")
    ok &= _assert(out["caption"] == "Caption body.", "caption preserved from flat top-level")
    ok &= _assert(out["hook"] == "A hook line.", "hook preserved")
    ok &= _assert(out["_source"] == "hermes_agent", "_source set")
    ok &= _assert("variations" not in out, "no variations key leaks into output")
    return ok


def test_3_empty_or_malformed_variations():
    print("[3] empty / malformed variations return None (fallback)")
    cases = [
        ("missing variations key", {"generated_at": "x", "agent": "post-differentiation-agent"}),
        ("empty variations list", {"variations": []}),
        ("variations not a list", {"variations": {"novel": "HA"}}),
        ("variations items lack caption", {"variations": [{"hook": "h", "novel": "HA"}]}),
        ("non-dict payload", "not a dict at all"),
        ("None payload", None),
    ]
    ok = True
    for label, payload in cases:
        out = _unwrap_variation(payload)
        ok &= _assert(out is None, f"rejected: {label}")
    return ok


def test_4_missing_caption_rejected():
    print("[4] missing caption is rejected (flat + wrapped)")
    ok = True
    flat_no_caption = {k: v for k, v in FLAT.items() if k != "caption"}
    ok &= _assert(_unwrap_variation(flat_no_caption) is None, "flat without caption -> None")
    wrapped_no_caption = {
        "variations": [{"hook": "h", "novel": "HA", "platform": "instagram", "content_angle": "x"}]
    }
    ok &= _assert(_unwrap_variation(wrapped_no_caption) is None, "wrapped without caption -> None")
    # caption present but empty string also rejected
    wrapped_empty_caption = {"variations": [dict(WRAPPED["variations"][0])]}
    wrapped_empty_caption["variations"][0]["caption"] = "   "
    ok &= _assert(_unwrap_variation(wrapped_empty_caption) is None, "wrapped with blank caption -> None")
    return ok


def test_5_fenced_and_prose_extraction():
    print("[5] fenced JSON + extra prose still extracted")
    ok = True
    fenced = (
        "Here is your payload:\n"
        "```json\n"
        + json.dumps(WRAPPED, ensure_ascii=False)
        + "\n```\n"
        "session_id: 20260805_145356_ae39a8\n"
    )
    parsed = _extract_json(fenced)
    ok &= _assert(isinstance(parsed, dict), "fenced JSON parsed")
    out = _unwrap_variation(parsed)
    ok &= _assert(out is not None and out["caption"] == "Wrapped caption body.", "fenced wrapped payload normalizes")

    prose = (
        "Sure, here is the post JSON:\n"
        + json.dumps(WRAPPED, ensure_ascii=False)
        + "\nLet me know if you need changes.\nsession_id: 20260805_145356_ae39a8\n"
    )
    parsed2 = _extract_json(prose)
    ok &= _assert(isinstance(parsed2, dict), "prose-wrapped JSON parsed")
    out2 = _unwrap_variation(parsed2)
    ok &= _assert(out2 is not None and out2["caption"] == "Wrapped caption body.", "prose-wrapped normalizes")

    flat_prose = (
        "payload below\n" + json.dumps(FLAT, ensure_ascii=False) + "\nsession_id: 20260805_145356_ae39a8\n"
    )
    out3 = _unwrap_variation(_extract_json(flat_prose))
    ok &= _assert(out3 is not None and out3["caption"] == "Caption body.", "flat prose-wrapped normalizes")
    return ok


def main():
    _assert.failed = 0
    results = [
        test_1_wrapped_normalizes(),
        test_2_flat_legacy_works(),
        test_3_empty_or_malformed_variations(),
        test_4_missing_caption_rejected(),
        test_5_fenced_and_prose_extraction(),
    ]
    print()
    if _assert.failed == 0 and all(results):
        print("ALL TESTS PASSED")
        return 0
    print(f"{_assert.failed} assertion(s) failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
