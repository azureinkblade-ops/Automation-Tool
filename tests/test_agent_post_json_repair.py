"""Bounded JSON repair regression tests for tools/agent_post_writer.py.

These pin the post-differentiation parser defect found in the live EN 37 run
(agent_post_runs row `agentpost_EN_37_20260807T142006_ad54a0`):
Hermes emitted a final block whose `hashtags` array had two elements with a
trailing quote but no opening quote (`#AzureInkblade"`, `#Cyberpunk"`). That is
invalid JSON, so the strict parse failed and the post silently fell back to the
generic template.

The fix adds a NARROW, array-context-only repair pass (after strict parsing
fails) that quotes unquoted hashtag array elements. It must never alter prose,
and must still fail soft when the object is genuinely unrecoverable.

Acceptance criteria (from the trace):
1. Hermes malformed final block -> strict JSON parse fails.
2. Bounded repair succeeds -> social-post-v1 validation succeeds.
3. AgentPostResult.copy populated, status = SUCCESS, parse_mode =
   "balanced_repair", normalizations includes "quoted_unquoted_hashtag_elements".
4. A deliberately unrecoverable malformed object still fails soft
   (FINAL_BLOCK_NOT_FOUND), never inventing content.

Run: python tests/test_agent_post_json_repair.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import agent_post_writer as aw  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")


# Exact Hermes output from the failed EN 37 run (selected_final_block), with the
# two malformed hashtag entries `#AzureInkblade"` and `#Cyberpunk"`.
EN37_MALFORMED_FINAL_BLOCK = """{
  "hook": "In a city built of glass code, only two things grant power: numbers on your screen.",
  "caption": "When the Neon rain stops screaming and Kael's system finally accepts his offer as its own, he finds himself not in control\\u2014but becoming something else entirely. The Soulblade wakes where it should never have been born.",
  "cta": "The soulblade cuts next chapter\\u2014read ahead on Patreon.",
  "hashtags": [ "#EternalNexus", #AzureInkblade", "#LitRPG", #Cyberpunk", "#Soulblade", "#NeonProgression", "#SciFiFantasy" ],
  "content_angle": "The system merging with the protagonist through cyber-dystopian horror.",
  "intended_audience": "LitRPG readers who prefer hard sci-fi elements to traditional RPG progression."
}"""

# A first-class valid object (control): strict parse path, no repair.
EN37_VALID = """{
  "hook": "In a city built of glass code, only two things grant power: numbers on your screen.",
  "caption": "When the Neon rain stops screaming and Kael's system finally accepts his offer as its own.",
  "cta": "The soulblade cuts next chapter\\u2014read ahead on Patreon.",
  "hashtags": ["#EternalNexus", "#AzureInkblade", "#LitRPG", "#Cyberpunk", "#Soulblade", "#NeonProgression", "#SciFiFantasy"],
  "content_angle": "cyber-dystopian horror",
  "intended_audience": "LitRPG readers"
}"""

# Deliberately unrecoverable: a truncated body missing its closing brace and with
# an unterminated string. Repair must NOT fabricate a result.
UNRECOVERABLE = """{
  "hook": "A hook that goes nowhere,
  "caption": "this object is truncated and has an unterminated string,
  "cta": "read ahead"""


def test_strict_parse_fails_on_en37_malformed():
    import json
    try:
        json.loads(EN37_MALFORMED_FINAL_BLOCK)
        strict_ok = True
    except json.JSONDecodeError:
        strict_ok = False
    check("EN37 malformed fails strict JSON parse", strict_ok, False)


def test_repair_recovers_en37_block():
    data, parse_mode, norms = aw._extract_json(EN37_MALFORMED_FINAL_BLOCK)
    check("EN37 repaired parse_mode", parse_mode, "balanced_repair")
    check("EN37 repair normalization label", "quoted_unquoted_hashtag_elements" in norms, True)
    check("EN37 repaired hashtags", data.get("hashtags"), [
        "#EternalNexus", "#AzureInkblade", "#LitRPG", "#Cyberpunk",
        "#Soulblade", "#NeonProgression", "#SciFiFantasy",
    ])
    check("EN37 repaired caption preserved verbatim",
          data.get("caption", "").startswith("When the Neon rain stops screaming"), True)
    # The em-dash defect token must NOT be invented or stripped from the caption.
    check("EN37 caption keeps em-dash char",
          "\\u2014" in EN37_MALFORMED_FINAL_BLOCK and "becoming something else entirely" in data.get("caption", ""), True)


def test_repaired_en37_passes_contract_and_unwraps():
    data, _, _ = aw._extract_json(EN37_MALFORMED_FINAL_BLOCK)
    unwrapped = aw._unwrap_variation(data)
    check("EN37 unwrapped not None", unwrapped is not None, True)
    missing, errs = aw._validate_contract(unwrapped)
    check("EN37 contract no missing fields", missing, [])
    check("EN37 contract no validation errors", errs, [])


def test_valid_object_skips_repair():
    data, parse_mode, norms = aw._extract_json(EN37_VALID)
    check("valid object parse_mode", parse_mode, "whole_text")
    check("valid object no repair normalizations", norms, ())
    check("valid object hashtags", data.get("hashtags", [])[:2], ["#EternalNexus", "#AzureInkblade"])


def test_unrecoverable_fails_soft():
    data, parse_mode, norms = aw._extract_json(UNRECOVERABLE)
    check("unrecoverable returns None", data, None)
    check("unrecoverable no parse_mode", parse_mode, None)


def test_repair_does_not_alter_prose():
    # The repair is syntax-only: a properly quoted string containing a hashtag
    # word must be left untouched (no spurious quoting inside strings).
    sample = '{"caption": "respect #webnovel and move on", "hashtags": ["#AzureInkblade", #LitRPG"]}'
    data, _, norms = aw._extract_json(sample)
    check("prose hashtag untouched", data.get("caption"), "respect #webnovel and move on")
    check("only the unquoted array element repaired",
          data.get("hashtags"), ["#AzureInkblade", "#LitRPG"])
    check("repair normalization recorded", "quoted_unquoted_hashtag_elements" in norms, True)


if __name__ == "__main__":
    for fn in [
        test_strict_parse_fails_on_en37_malformed,
        test_repair_recovers_en37_block,
        test_repaired_en37_passes_contract_and_unwraps,
        test_valid_object_skips_repair,
        test_unrecoverable_fails_soft,
        test_repair_does_not_alter_prose,
    ]:
        fn()
    if FAILS:
        print("FAIL")
        for f in FAILS:
            print(" -", f)
        raise SystemExit(1)
    print("OK")
