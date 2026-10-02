"""Hand-specific prompt bank for regional repair.

Keep prompts here so the Visual Director and object_refinement engine stay free
of hand policy. Add new variants carefully; prefer small, testable changes.
"""

from __future__ import annotations

DEFAULT_HAND_PROMPT = (
    "anatomically correct human hands, five fingers, natural proportions, "
    "detailed knuckles and fingernails, correct finger count, no extra fingers, "
    "no missing fingers, no fused fingers, clean skin, sharp focus on hands"
)

DEFAULT_HAND_NEGATIVE = (
    "extra fingers, missing fingers, fused fingers, mutated hands, poorly drawn hands, "
    "bad anatomy, deformed hands, too many fingers, fewer than five fingers, "
    "blurry hands, ugly hands, distorted fingers"
)

REGION_PROMPTS = {
    "hands": DEFAULT_HAND_PROMPT,
    "both": DEFAULT_HAND_PROMPT,
    "left_hand": "anatomically correct left hand, five fingers, natural proportions, detailed knuckles",
    "right_hand": "anatomically correct right hand, five fingers, natural proportions, detailed knuckles",
}


def get_hand_prompt(region: str = "hands", override: str | None = None) -> str:
    if override and override.strip():
        return override.strip()
    return REGION_PROMPTS.get(region, DEFAULT_HAND_PROMPT)


def get_hand_negative(override: str | None = None) -> str:
    if override and override.strip():
        return override.strip()
    return DEFAULT_HAND_NEGATIVE
