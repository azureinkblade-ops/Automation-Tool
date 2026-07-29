"""
novel_voice.py - Per-novel voice banks for Azure Inkblade social copy.

Pure data + pure lookup helpers only. MUST NOT import app.py (circular
dependency risk). app.py retains orchestration, rotation, and chapter
extraction; this module supplies the novel-specific framing material.

Determinism: any internal selection uses hashlib.sha256, never the built-in
hash(), so results are stable across process restarts (see regression test
for rotated_hashtags / seed stability).

Voice directions (from the caption-voice-rotation brief):
  EN: betrayal, systems, shadow-forging, tactical consequences
  HA: survival, modern cultivation, System pressure, hidden heavenly rules
  SF: forging, sacrifice, power costs, fire and transformation
  HP: trials, discipline, cultivation philosophy, incremental advancement

Compositional design (brief): 8 hook frames per novel + 4 voice modifiers per
novel + shared CTA variants + shared engagement frames. Combining an extracted
chapter hook with these yields far more than 8 final strings without maintaining
hundreds of near-identical sentences. CTA goals are SHARED; the novel affects
expression (via modifiers), not which goal is chosen.
"""

import hashlib
from typing import Dict, List

# ---------------------------------------------------------------------------
# Per-novel voice profiles
# ---------------------------------------------------------------------------
# hook_frames: 8 concrete framing patterns per novel. These FRAME an extracted
#   chapter hook; they never replace chapter fact.
# voice_modifiers: 4 per novel. Applied to the extracted hook to set novel tone.
# tone_terms: flavor vocabulary used by caption assembly / tests.
NOVEL_VOICE_PROFILES: Dict[str, Dict[str, List[str]]] = {
    "EN": {
        "hook_frames": [
            "The system that forged him just marked him a threat.",
            "One ally's silence cost three squads their lives.",
            "He shadow-forged a weapon the architects never logged.",
            "The tactic that won the battle broke the alliance.",
            "A buried log exposed the hand that betrayed the line.",
            "Every upgrade came with a leash someone forgot to hide.",
            "The forging pit remembered a name command erased.",
            "His countermove left the system owing him a debt.",
        ],
        "voice_modifiers": [
            "tactical",
            "system-bound",
            "betrayal-weighted",
            "consequence-driven",
        ],
        "tone_terms": [
            "betrayal",
            "systems",
            "shadow-forge",
            "tactical",
        ],
    },
    "HA": {
        "hook_frames": [
            "The System's quota left no room for the weak to breathe.",
            "A hidden heavenly rule rewrote what survival cost.",
            "Modern cultivation meant rent was due in spiritual coin.",
            "The pressure that broke others forged his next step.",
            "He read the small print the sects never taught.",
            "One overlooked statute turned a death sentence into a ladder.",
            "The heavenly audit skipped him, and he kept moving.",
            "Survival meant out-reading the rule that governed the rest.",
        ],
        "voice_modifiers": [
            "survival-weighted",
            "modern-cultivation",
            "System-pressure",
            "hidden-rule",
        ],
        "tone_terms": [
            "survival",
            "cultivation",
            "System",
            "heavenly-rules",
        ],
    },
    "SF": {
        "hook_frames": [
            "The forge took a year of his life for a single edge.",
            "Every spark of power burned something he couldn't reclaim.",
            "She tempered the blade in the cost she refused to name.",
            "Transformation demanded the part of him that feared fire.",
            "The price of the weapon was the hand that held it.",
            "He forged the pact in the heat of what he'd lost.",
            "Power came measured in what the flame consumed.",
            "The transformation finished what the sacrifice began.",
        ],
        "voice_modifiers": [
            "forge-weighted",
            "sacrifice-bound",
            "fire-transformation",
            "cost-aware",
        ],
        "tone_terms": [
            "forge",
            "sacrifice",
            "fire",
            "transformation",
        ],
    },
    "HP": {
        "hook_frames": [
            "The trial wasn't a test of strength but of restraint.",
            "Discipline turned a single breath into a breakthrough.",
            "His philosophy outlasted every genius who rushed the path.",
            "Incremental advancement meant the mountain moved a grain at a time.",
            "The trial cleared those who mistook speed for progress.",
            "He trained the habit that made the mastery inevitable.",
            "Cultivation was a question he answered daily, not once.",
            "The small discipline compounded into the wall others couldn't pass.",
        ],
        "voice_modifiers": [
            "trial-weighted",
            "discipline-bound",
            "philosophy-led",
            "incremental",
        ],
        "tone_terms": [
            "trials",
            "discipline",
            "philosophy",
            "advancement",
        ],
    },
}

# ---------------------------------------------------------------------------
# Shared CTA variants (goal set is shared; novel affects wording, not goal)
# 6 variants per goal. Patreon kept largely hashtag-free by the caller.
# ---------------------------------------------------------------------------
SHARED_CTA_VARIANTS: Dict[str, List[str]] = {
    "read": [
        "Read the new chapter free on Royal Road.",
        "Start the chapter now, link in bio.",
        "Catch up on the latest release today.",
        "Open the new chapter and see what breaks.",
        "The new chapter is live, read it here.",
        "Dive into the latest chapter now.",
    ],
    "follow": [
        "Follow for the next chapter drop.",
        "Tap follow so you don't miss the next beat.",
        "Follow along as the arc unfolds.",
        "Stay with the story, hit follow.",
        "Follow for daily worldbuilding drops.",
        "Keep up with the saga, follow now.",
    ],
    "subscribe": [
        "Subscribe on Patreon for early access.",
        "Get chapters early, subscribe on Patreon.",
        "Support the work and subscribe for drafts.",
        "Subscribe for the paid advance chapters.",
        "Become a patron for the next arc first.",
        "Subscribe to read ahead of the queue.",
    ],
    "comment": [
        "What would you trade to reach the top? Reply below.",
        "Which path would you have taken? Comment.",
        "Drop your theory in the replies.",
        "Tell me your read on that twist.",
        "What broke first, the blade or the bond? Comment.",
        "Whose side are you on? Let me know below.",
    ],
    "support": [
        "Support the serial on Patreon to keep it free.",
        "If the story earned it, back it on Patreon.",
        "Your support funds the next hundred chapters.",
        "Help the work stay ad-free, support on Patreon.",
        "Back the author and unlock early drafts.",
        "Keep the chapters coming, support the serial.",
    ],
    "save": [
        "Save this for your next reading break.",
        "Bookmark it for later, save now.",
        "Save and come back when the night is long.",
        "Pin this to your TBR, save here.",
        "Save it before the算法 buries it.",
        "Keep this one, hit save.",
    ],
}

# ---------------------------------------------------------------------------
# Shared engagement frames (platform-shaped, novel-agnostic; novel tone comes
# from modifiers applied by the caller). 5-6 per platform/style.
# ---------------------------------------------------------------------------
ENGAGEMENT_FRAMES: Dict[str, List[str]] = {
    "x": [
        "Which line hit hardest? Quote it.",
        "Reply with your build for this arc.",
        "Tag the friend who'd main this path.",
        "What's the worst power cost you'd accept?",
        "Drop a / for the next chapter ping.",
        "RT if the System owed you one too.",
    ],
    "instagram": [
        "Save this & follow for the next chapter.",
        "Tag someone who needs this arc.",
        "Which frame would you hang? Comment.",
        "Story your read in the replies.",
        "Share to stories if the hook landed.",
        "Follow for daily ink-drop art.",
    ],
    "facebook": [
        "What would you sacrifice for that power?",
        "Tell us your favorite moment so far.",
        "Share with a friend who loves the genre.",
        "Comment your theory on the ending.",
        "Follow for more from this world.",
    ],
    "patreon": [
        "Patrons get the next arc first, join here.",
        "Early drafts are live for supporters.",
        "Comment in the patron thread with your take.",
        "Which bonus should we unlock next?",
        "Thanks for keeping the serial free to readers.",
    ],
}

# ---------------------------------------------------------------------------
# Pure lookup helpers (no side effects, deterministic selection)
# ---------------------------------------------------------------------------
def _stable_index(key: str, pool_size: int) -> int:
    """Deterministic 0..pool_size-1 from a string key. Uses SHA-256."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % pool_size


def get_hook_frames(abbr: str) -> List[str]:
    return list(NOVEL_VOICE_PROFILES.get(abbr, {}).get("hook_frames", []))


def get_voice_modifiers(abbr: str) -> List[str]:
    return list(NOVEL_VOICE_PROFILES.get(abbr, {}).get("voice_modifiers", []))


def get_tone_terms(abbr: str) -> List[str]:
    return list(NOVEL_VOICE_PROFILES.get(abbr, {}).get("tone_terms", []))


def select_hook_frame(abbr: str, seed: str) -> str:
    """Deterministic hook-frame pick for a novel + seed (stable across restarts)."""
    frames = get_hook_frames(abbr)
    if not frames:
        return ""
    return frames[_stable_index(f"{abbr}:{seed}:hook", len(frames))]


def select_voice_modifier(abbr: str, seed: str) -> str:
    mods = get_voice_modifiers(abbr)
    if not mods:
        return ""
    return mods[_stable_index(f"{abbr}:{seed}:mod", len(mods))]


def apply_voice_modifier(frame: str, modifier: str) -> str:
    """Compose an extracted chapter hook with a novel voice modifier.

    The modifier labels the framing; it never alters the chapter fact.
    """
    if not modifier:
        return frame
    return f"{frame} [{modifier}]"


def get_cta_variants(goal: str) -> List[str]:
    return list(SHARED_CTA_VARIANTS.get(goal, []))


def select_cta_variant(goal: str, seed: str) -> str:
    variants = get_cta_variants(goal)
    if not variants:
        return ""
    return variants[_stable_index(f"{goal}:{seed}:cta", len(variants))]


def get_engagement_frames(platform: str) -> List[str]:
    return list(ENGAGEMENT_FRAMES.get(platform, []))


def select_engagement_frame(platform: str, seed: str) -> str:
    frames = get_engagement_frames(platform)
    if not frames:
        return ""
    return frames[_stable_index(f"{platform}:{seed}:eng", len(frames))]
