"""Canonical novel-id normalization seam (SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R2, Part A).

One deterministic seam used before Visual Director, AIVSB, SceneEnvironmentSpec,
location resolution, scene composition and observability.

Accepted production forms ONLY (case / surrounding-whitespace / inner-whitespace tolerant):
  short codes : HA, EN, HP, HFP, SF
  full names  : 'Heavenly Ascension System', 'Eternal Nexus', 'Hundredfold Path',
                'The Hundredfold Path', 'Soul Forge Era'
  extra form  : 'Soulforge Era' (documented: production code demonstrably uses it)
Documented production provenance of each form:
  HA/EN/HP/SF + the four NOVEL_NAMES values ............ app.py NOVEL_NAMES
  HFP ................................................... chapter_cron_handoff.normalize_daily_abbr
  'The Hundredfold Path' ................................ app.py ROYAL_ROAD_URLS / DOCS_NOVEL_FILES title,
                                                          studio_bible_adapter._FULL_TITLE_TO_NOVEL_ID
  'Soulforge Era' ....................................... app_config.NOVEL_NAMES['SF'] (used by
                                                          promo_copy.story_key), app.py novel picker
                                                          ['SF', 'Soulforge Era'], DOCS_NOVEL_FILES
No other aliases are accepted (unknown -> None, never a guess).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

CANONICAL_NOVEL_IDS: Tuple[str, ...] = ("ha", "en", "hp", "sf")

_SHORT_CODES: Dict[str, str] = {
    "ha": "ha",
    "en": "en",
    "hp": "hp",
    "hfp": "hp",
    "sf": "sf",
}

FULL_NAME_TO_CANONICAL_NOVEL_ID: Dict[str, str] = {
    "heavenly ascension system": "ha",
    "eternal nexus": "en",
    "hundredfold path": "hp",
    "the hundredfold path": "hp",
    "soul forge era": "sf",
    "soulforge era": "sf",  # app_config.NOVEL_NAMES['SF'] (production form, see module doc)
}

ACCEPTED_FORMS: Tuple[str, ...] = tuple(sorted(set(_SHORT_CODES) | set(FULL_NAME_TO_CANONICAL_NOVEL_ID)))


def _key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def normalize_novel_id(value: Any) -> Optional[str]:
    """Return the canonical lowercase novel id ('ha'|'en'|'hp'|'sf') or None."""
    k = _key(value)
    if not k:
        return None
    if k in _SHORT_CODES:
        return _SHORT_CODES[k]
    return FULL_NAME_TO_CANONICAL_NOVEL_ID.get(k)


def resolve_novel_for_scene(*candidates: Any) -> Tuple[str, str, bool]:
    """(input_value, normalized_or_fallback, resolved).

    Tries each candidate in order (e.g. novel, then title). When none resolves the
    first non-empty candidate is returned lowercased (legacy behaviour) with
    resolved=False so callers/observability can report NOVEL_UNRESOLVED.
    """
    first = ""
    for c in candidates:
        s = str(c or "").strip()
        if not s:
            continue
        if not first:
            first = s
        nid = normalize_novel_id(s)
        if nid:
            return s, nid, True
    return first, first.lower(), False


def novel_normalization_record(value: Any) -> Dict[str, Any]:
    nid = normalize_novel_id(value)
    return {
        "INPUT_NOVEL_VALUE": "" if value is None else str(value),
        "NORMALIZED_NOVEL_ID": nid or "UNRESOLVED",
        "NOVEL_RESOLVED": bool(nid),
    }
