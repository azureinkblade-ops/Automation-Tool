"""Compact local-SDXL prompt composer (V1:local_stable_diffusion only).

Assembles governed structural identity + wardrobe heads at runtime for explicit-character
requests, enforces the 75-token dual CLIP content window (after BOS/EOS), and fail-closes
on required overflow / silent truncation.

RUNTIME_HEAD_SOURCE=GOVERNED_STRUCTURAL_FIELDS
PRIVATE_HEAD_DIRECTORY_REQUIRED_AT_RUNTIME=NO
Does not load C:\\Users\\David\\Documents\\stage2-private-heads.
Does not change Stage-1 resolve_governed_binding semantics or ComfyUI V2 prompt path.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

PATH_ID = "V1:local_stable_diffusion"
SEPARATOR = ", "
USABLE_CONTENT_WINDOW = 75
SILENT_TOKENIZER_TRUNCATION_ALLOWED = False
LORA_TRIGGER_CAN_BE_DROPPED_FOR_BUDGET = True
RUNTIME_HEAD_SOURCE = "GOVERNED_STRUCTURAL_FIELDS"
PRIVATE_HEAD_DIRECTORY_REQUIRED_AT_RUNTIME = False

BUDGETS: Dict[str, int] = {
    "IDENTITY": 20,
    "WARDROBE": 10,
    "ENVIRONMENT": 12,
    "ACTION": 8,
    "EFFECT": 10,
    "PROP": 5,
    "CAMERA": 6,
    "LORA_TRIGGER": 4,
}

PRIORITY_KEYS: Tuple[str, ...] = (
    "IDENTITY",
    "WARDROBE",
    "ENVIRONMENT",
    "ACTION",
    "EFFECT",
    "PROP",
    "CAMERA",
    "LORA_TRIGGER",
)

REQUIRED_KEYS = frozenset({
    "IDENTITY",
    "WARDROBE",
    "ENVIRONMENT",
    "ACTION",
    "EFFECT",
    "PROP",
})

OPTIONAL_DROP_ORDER: Tuple[str, ...] = (
    "LORA_TRIGGER",
    "CAMERA",
    "PROP",
    "EFFECT",
)

PINNED_IDENTITY_SHA256: Dict[str, str] = {
    "kai": "542912baa0121e5ae186bf73677066069f96f068e25c2e5d022540cb1034550a",
    "kael_veyra": "b17b9361ad37046a17154c22d9b02fa4ea8b59987b5fd1bc6ae9207cd8d4df18",
    "kael": "b17b9361ad37046a17154c22d9b02fa4ea8b59987b5fd1bc6ae9207cd8d4df18",
    "liang": "1ace9a98a46cdc102804084b27498dd9189f95e637f473fa6ebe1a0c0764e1d1",
    "jarek": "8f2979987f0d3e60a534b1939805b20cd6ec5f9fd5679917e122dd4ccd2ec74e",
}
PINNED_WARDROBE_SHA256: Dict[str, str] = {
    "kai": "31175ecc164ee727d1caec3293aa62a48e3c2f843f72328784961ec2208b1a31",
    "kael_veyra": "12c03a54e8019ddd608586141bbd02e138f3b6f30a0105c4271f0ed51be4d747",
    "kael": "12c03a54e8019ddd608586141bbd02e138f3b6f30a0105c4271f0ed51be4d747",
    "liang": "9c795083befe183c3ab952ede40e83425ac06eebe23eedfefef096aaba98c7fe",
    "jarek": "79f4ccc2ac59c50ffaaab2c0348a25dff2e9a6fbd7c5f2197853c829b9b0a53e",
}

_ROOT = Path(__file__).resolve().parent.parent


class CompactPromptError(Exception):
    """Fail-closed diagnostic for compact local-SDXL prompt composition."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail or "")
        super().__init__(f"{self.code}:{self.detail}" if self.detail else self.code)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def join_parts(parts: Sequence[str]) -> str:
    return SEPARATOR.join(p for p in parts if p and str(p).strip())


def _humanize_token(value: str) -> str:
    return str(value or "").replace("_", " ").strip()


def _compact_display_name(display_name: str) -> str:
    parts = str(display_name or "").strip().split()
    return parts[0] if parts else ""


def _compact_age(character_id: str, age_required: str) -> str:
    age = str(age_required or "").strip()
    if not age:
        return ""
    if age.isdigit():
        if character_id == "kai":
            return f"{age} year old"
        return age
    return _humanize_token(age)


def _compact_hair(character_id: str, hair_required: Sequence[str], lock_tokens: Sequence[str]) -> str:
    if character_id == "jarek":
        return "wild hair"
    for tok in lock_tokens:
        t = str(tok).strip().lower()
        if "hair" in t:
            return str(tok).strip()
    if hair_required:
        base = _humanize_token(str(hair_required[0]).split("/")[0])
        return base if base.endswith("hair") else f"{base} hair"
    return ""


def _compact_eyes(character_id: str, eye_color_required: str, lock_tokens: Sequence[str]) -> str:
    if not eye_color_required:
        return ""
    for tok in lock_tokens:
        t = str(tok).strip().lower()
        if "eye" in t:
            return str(tok).strip().replace("-", " ")
    human = _humanize_token(eye_color_required)
    return human if human.endswith("eyes") else f"{human} eyes"


def assemble_identity_head(character_id: str) -> Tuple[str, Tuple[str, ...]]:
    """Assemble compact identity head from GOVERNED_IDENTITY_CONTRACTS structural fields."""
    from tools.identity_preservation import (
        GOVERNED_IDENTITY_CONTRACTS,
        normalize_identity_character_key,
    )

    key = normalize_identity_character_key(character_id)
    if not key or key not in GOVERNED_IDENTITY_CONTRACTS:
        raise CompactPromptError("UNKNOWN_GOVERNED_CHARACTER", str(character_id))
    c = GOVERNED_IDENTITY_CONTRACTS[key]
    labels: List[str] = []
    parts: List[str] = []

    parts.append(_compact_display_name(c.display_name))
    age_bit = _compact_age(key, c.age_required)
    if age_bit:
        parts.append(age_bit)
        labels.append("age")
    if c.sex:
        parts.append(str(c.sex).strip())
        labels.append("sex")
    build_bit = _humanize_token(c.build_required)
    if build_bit:
        parts.append(build_bit)
        labels.append("build")
    if any("height" in _humanize_token(x).lower() for x in (c.build_allowed or ())):
        labels.append("height")
    hair_bit = _compact_hair(key, c.hair_required, c.lock_tokens)
    if hair_bit:
        parts.append(hair_bit)
        labels.append("hair_style")
    eyes_bit = _compact_eyes(key, c.eye_color_required, c.lock_tokens)
    if eyes_bit:
        parts.append(eyes_bit)
        labels.append("eyes")
    labels.append("species")
    labels.append("character_id")

    head = join_parts(parts)
    pinned = PINNED_IDENTITY_SHA256.get(key) or PINNED_IDENTITY_SHA256.get(str(character_id))
    if pinned and sha256_text(head) != pinned:
        raise CompactPromptError(
            "IDENTITY_HEAD_SHA256_DRIFT",
            f"character_id={key} got={sha256_text(head)} expected={pinned}",
        )
    if key == "jarek" and "16" not in head:
        raise CompactPromptError("JAREK_AGE16_PRESERVED", "missing")
    if key == "liang" and c.sex is not None:
        raise CompactPromptError("LIANG_GENDER_INVENTED", "sex must remain unspecified")
    return head, tuple(labels)


def _wardrobe_contract_key(character_id: str) -> str:
    from tools.wardrobe_preservation import normalize_character_key
    return normalize_character_key(character_id)


def _compact_wardrobe_minimum(character_key: str, text_canon: Sequence[str]) -> str:
    """TEXT_CANON_WARDROBE minimum projection (deterministic; no private-dir load)."""
    items = [str(x).strip() for x in text_canon if str(x).strip()]
    if not items:
        return ""
    key = character_key
    if key in ("kael", "kael_veyra"):
        return items[0].split("(")[0].strip().replace("_", " ")
    if key == "liang":
        return items[0].replace("_", " ")
    if key == "jarek":
        raw = items[0].replace("_", " ")
        bits = raw.split()
        if bits == ["scavenger", "rags", "oil", "stained"]:
            return "scavenger oil-stained rags"
        return raw
    if key == "kai":
        first = items[0].split("(")[0].strip()
        second = items[1].split("(")[0].strip() if len(items) > 1 else ""
        toks = first.split("_")
        color = toks[0] if toks else ""
        garment = next((t for t in toks if t in {"shirt", "pants", "robe", "robes", "wear", "rags"}), "shirt")
        logo = "logo" if any("logo" in t or t == "faded" for t in toks) else ""
        torso = " ".join(x for x in (color, logo, garment) if x)
        pants = second.replace("_", " ")
        return join_parts([torso, pants])
    return items[0].split("(")[0].strip().replace("_", " ")


def assemble_wardrobe_head(character_id: str) -> str:
    """Assemble compact wardrobe head from TEXT_CANON_WARDROBE minimum only."""
    from tools.wardrobe_preservation import load_contract

    key = _wardrobe_contract_key(character_id)
    contract = load_contract(key)
    text_canon = contract.get("TEXT_CANON_WARDROBE") or []
    head = _compact_wardrobe_minimum(key, text_canon)
    pin_key = "kael_veyra" if key == "kael" else key
    pinned = PINNED_WARDROBE_SHA256.get(pin_key) or PINNED_WARDROBE_SHA256.get(key)
    if pinned and sha256_text(head) != pinned:
        raise CompactPromptError(
            "WARDROBE_HEAD_SHA256_DRIFT",
            f"character_id={key} got={sha256_text(head)} expected={pinned}",
        )
    return head


class TokenizerUnavailable(CompactPromptError):
    def __init__(self, detail: str = "") -> None:
        super().__init__("requires_sdxl_tokenizer", detail)


def resolve_tokenizer_dirs() -> Tuple[Path, Path]:
    """Return (tokenizer CLIP-L, tokenizer_2 CLIP-G) dirs.

    Search order:
      1) LOCAL_SD_MODEL / tokenizer{,_2}
      2) repo models/sdxl-base/tokenizer{,_2}
      3) tests/fixtures/sdxl_base_tokenizers/tokenizer{,_2}  (Linux CI tokenizer-only)
    """
    cands: List[Path] = []
    env_model = os.environ.get("LOCAL_SD_MODEL", "").strip()
    if env_model:
        p = Path(env_model)
        base = p if p.is_absolute() else _ROOT / p
        cands.append(base)
    cands.append(_ROOT / "models" / "sdxl-base")
    cands.append(_ROOT / "tests" / "fixtures" / "sdxl_base_tokenizers")
    for base in cands:
        t1 = base / "tokenizer"
        t2 = base / "tokenizer_2"
        if (
            (t1 / "vocab.json").exists()
            and (t1 / "merges.txt").exists()
            and (t2 / "vocab.json").exists()
            and (t2 / "merges.txt").exists()
        ):
            return t1, t2
    raise TokenizerUnavailable(
        "CLIP-L/G tokenizer folders not found under models/sdxl-base or "
        "tests/fixtures/sdxl_base_tokenizers (vocab.json+merges.txt required for both)"
    )


@lru_cache(maxsize=1)
def _load_clip_tokenizers() -> Tuple[Any, Any, str, str]:
    try:
        from transformers import CLIPTokenizer
    except Exception as exc:  # noqa: BLE001
        raise TokenizerUnavailable(f"transformers.CLIPTokenizer import failed: {exc}") from exc
    t1, t2 = resolve_tokenizer_dirs()
    tok_l = CLIPTokenizer.from_pretrained(str(t1), local_files_only=True)
    tok_g = CLIPTokenizer.from_pretrained(str(t2), local_files_only=True)
    return tok_l, tok_g, str(t1), str(t2)


def content_token_count(tokenizer: Any, text: str) -> int:
    ids = tokenizer.encode(text, add_special_tokens=True, truncation=False)
    ids2 = list(ids)
    bos = getattr(tokenizer, "bos_token_id", None)
    eos = getattr(tokenizer, "eos_token_id", None)
    if ids2 and bos is not None and ids2[0] == bos:
        ids2 = ids2[1:]
    if ids2 and eos is not None and ids2[-1] == eos:
        ids2 = ids2[:-1]
    return len(ids2)


def dual_content_token_counts(text: str) -> Tuple[int, int]:
    tok_l, tok_g, _, _ = _load_clip_tokenizers()
    return content_token_count(tok_l, text), content_token_count(tok_g, text)


def assert_within_slot_budget(text: str, budget: int, *, slot: str) -> Tuple[int, int]:
    e1, e2 = dual_content_token_counts(text)
    if e1 > budget or e2 > budget:
        raise CompactPromptError(
            "REQUIRED_SLOT_OVER_BUDGET",
            f"slot={slot} budget={budget} encoder1={e1} encoder2={e2} silent_truncation_forbidden",
        )
    return e1, e2


@dataclass
class CompactComposeResult:
    prompt: str
    upstream_character_assigned: str
    character_id: Optional[str]
    segments: Dict[str, str] = field(default_factory=dict)
    segment_token_counts_l: Dict[str, int] = field(default_factory=dict)
    segment_token_counts_g: Dict[str, int] = field(default_factory=dict)
    encoder1_content_tokens: int = 0
    encoder2_content_tokens: int = 0
    dropped_optional: Tuple[str, ...] = ()
    identity_sha256: Optional[str] = None
    wardrobe_sha256: Optional[str] = None
    identity_field_labels: Tuple[str, ...] = ()
    path_id: str = PATH_ID
    runtime_head_source: str = RUNTIME_HEAD_SOURCE
    diagnostic: str = ""

    def to_metrics(self) -> Dict[str, Any]:
        return {
            "PATH_ID": self.path_id,
            "UPSTREAM_CHARACTER_ASSIGNED": self.upstream_character_assigned,
            "CHARACTER_ID": self.character_id,
            "ENCODER1_CONTENT_TOKENS": self.encoder1_content_tokens,
            "ENCODER2_CONTENT_TOKENS": self.encoder2_content_tokens,
            "DROPPED_OPTIONAL": list(self.dropped_optional),
            "IDENTITY_SHA256": self.identity_sha256,
            "WARDROBE_SHA256": self.wardrobe_sha256,
            "IDENTITY_FIELD_LABELS": list(self.identity_field_labels),
            "RUNTIME_HEAD_SOURCE": self.runtime_head_source,
            "PROMPT_SHA256": sha256_text(self.prompt),
            "PROMPT_CHAR_LEN": len(self.prompt),
            "SEGMENT_KEYS": [k for k, v in self.segments.items() if v],
            "DIAGNOSTIC": self.diagnostic,
        }


def _normalize_upstream(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"YES", "NO", "UNKNOWN"}:
        return raw
    if raw in {"", "NONE", "NULL"}:
        return "UNKNOWN"
    raise CompactPromptError("INVALID_UPSTREAM_CHARACTER_ASSIGNED", raw)


def compose_local_sdxl_compact_prompt(
    *,
    upstream_character_assigned: Any,
    character_id: Optional[str] = None,
    environment: str = "",
    action: str = "",
    effect: str = "",
    effect_required: bool = True,
    prop: str = "",
    prop_required: bool = True,
    camera: str = "",
    lora_trigger: str = "",
    path_id: str = PATH_ID,
) -> CompactComposeResult:
    """Compose a compact V1 local-SDXL prompt inside the 75-token dual-CLIP window.

    UPSTREAM_CHARACTER_ASSIGNED:
      YES -> include compact governed identity (+ wardrobe when governed)
      NO  -> no protagonist identity or protagonist wardrobe
      UNKNOWN -> fail closed (Stage-1 semantics preserved)
    """
    if path_id != PATH_ID:
        raise CompactPromptError("PATH_ID_OUT_OF_SCOPE", path_id)

    upstream = _normalize_upstream(upstream_character_assigned)
    if upstream == "UNKNOWN":
        raise CompactPromptError(
            "FAIL_CLOSED_NO_NEW_PROTAGONIST_FALLBACK:UPSTREAM_CHARACTER_ASSIGNED_UNKNOWN",
            "compact composer refuses UNKNOWN",
        )

    segments: Dict[str, str] = {
        "IDENTITY": "",
        "WARDROBE": "",
        "ENVIRONMENT": str(environment or "").strip(),
        "ACTION": str(action or "").strip(),
        "EFFECT": str(effect or "").strip(),
        "PROP": str(prop or "").strip(),
        "CAMERA": str(camera or "").strip(),
        "LORA_TRIGGER": str(lora_trigger or "").strip(),
    }
    id_labels: Tuple[str, ...] = ()
    id_sha: Optional[str] = None
    w_sha: Optional[str] = None
    cid_norm: Optional[str] = None

    if upstream == "YES":
        if not character_id:
            raise CompactPromptError("CHARACTER_ID_REQUIRED_WHEN_UPSTREAM_YES", "")
        id_head, id_labels = assemble_identity_head(character_id)
        w_head = assemble_wardrobe_head(character_id)
        segments["IDENTITY"] = id_head
        segments["WARDROBE"] = w_head
        id_sha = sha256_text(id_head)
        w_sha = sha256_text(w_head)
        from tools.identity_preservation import normalize_identity_character_key
        cid_norm = normalize_identity_character_key(character_id)
    else:
        segments["IDENTITY"] = ""
        segments["WARDROBE"] = ""
        cid_norm = None

    slot_counts_l: Dict[str, int] = {}
    slot_counts_g: Dict[str, int] = {}
    for key, text in list(segments.items()):
        if not text:
            slot_counts_l[key] = 0
            slot_counts_g[key] = 0
            continue
        budget = BUDGETS[key]
        e1, e2 = dual_content_token_counts(text)
        slot_counts_l[key] = e1
        slot_counts_g[key] = e2
        is_required = key in REQUIRED_KEYS
        if key == "EFFECT" and not effect_required:
            is_required = False
        if key == "PROP" and not prop_required:
            is_required = False
        if key in ("IDENTITY", "WARDROBE") and upstream != "YES":
            is_required = False
        if (e1 > budget or e2 > budget) and is_required:
            raise CompactPromptError(
                "REQUIRED_SLOT_OVER_BUDGET",
                f"slot={key} budget={budget} encoder1={e1} encoder2={e2} "
                f"SILENT_TOKENIZER_TRUNCATION_ALLOWED=NO",
            )
        if (e1 > budget or e2 > budget) and not is_required:
            segments[key] = ""
            slot_counts_l[key] = 0
            slot_counts_g[key] = 0

    optional_present: List[str] = []
    for key in OPTIONAL_DROP_ORDER:
        if not segments.get(key):
            continue
        if key == "PROP" and prop_required:
            continue
        if key == "EFFECT" and effect_required:
            continue
        if key in ("IDENTITY", "WARDROBE"):
            continue
        optional_present.append(key)

    dropped: List[str] = []
    kept_keys = [k for k in PRIORITY_KEYS if segments.get(k)]
    prompt = join_parts([segments[k] for k in kept_keys])
    e1, e2 = dual_content_token_counts(prompt)

    while (e1 > USABLE_CONTENT_WINDOW or e2 > USABLE_CONTENT_WINDOW) and optional_present:
        drop_key = optional_present.pop(0)
        if not segments.get(drop_key):
            continue
        segments[drop_key] = ""
        dropped.append(drop_key)
        kept_keys = [k for k in PRIORITY_KEYS if segments.get(k)]
        prompt = join_parts([segments[k] for k in kept_keys])
        e1, e2 = dual_content_token_counts(prompt)

    if e1 > USABLE_CONTENT_WINDOW or e2 > USABLE_CONTENT_WINDOW:
        raise CompactPromptError(
            "REQUIRED_PROMPT_EXCEEDS_CONTENT_WINDOW",
            f"encoder1={e1} encoder2={e2} window={USABLE_CONTENT_WINDOW} "
            f"SILENT_TOKENIZER_TRUNCATION_ALLOWED=NO dropped={dropped}",
        )

    return CompactComposeResult(
        prompt=prompt,
        upstream_character_assigned=upstream,
        character_id=cid_norm,
        segments={k: v for k, v in segments.items() if v},
        segment_token_counts_l={k: slot_counts_l.get(k, 0) for k in segments if segments.get(k)},
        segment_token_counts_g={k: slot_counts_g.get(k, 0) for k in segments if segments.get(k)},
        encoder1_content_tokens=e1,
        encoder2_content_tokens=e2,
        dropped_optional=tuple(dropped),
        identity_sha256=id_sha,
        wardrobe_sha256=w_sha,
        identity_field_labels=id_labels,
    )


def character_needles_for_leak_check() -> Tuple[str, ...]:
    """Structural character id / display needles for INTENT_NO leak checks (no private prose)."""
    from tools.identity_preservation import GOVERNED_IDENTITY_CONTRACTS
    needles: List[str] = []
    for c in GOVERNED_IDENTITY_CONTRACTS.values():
        needles.append(c.character_id)
        needles.append(c.display_name)
        needles.extend(c.aliases)
    out = []
    seen = set()
    for n in needles:
        s = str(n or "").strip()
        if s and s.casefold() not in seen:
            seen.add(s.casefold())
            out.append(s)
    return tuple(out)


def apply_compact_slots_for_v1(
    *,
    upstream_character_assigned: Any,
    character_id: Optional[str] = None,
    environment: str = "",
    action: str = "",
    effect: str = "",
    effect_required: bool = True,
    prop: str = "",
    prop_required: bool = True,
    camera: str = "",
    lora_trigger: str = "",
) -> CompactComposeResult:
    """Public V1 entry: compose compact prompt (PATH_ID locked inside)."""
    return compose_local_sdxl_compact_prompt(
        upstream_character_assigned=upstream_character_assigned,
        character_id=character_id,
        environment=environment,
        action=action,
        effect=effect,
        effect_required=effect_required,
        prop=prop,
        prop_required=prop_required,
        camera=camera,
        lora_trigger=lora_trigger,
        path_id=PATH_ID,
    )


def try_rewrite_prompt_with_compact_slots(
    prompt: str,
    *,
    compact_slots: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """If compact_slots provided, replace freeform prompt with composer output.

    Returns None when compact_slots is absent/empty (caller keeps original prompt).
    Narrow V1 wire — does not alter ComfyUI V2 or Stage-1 binding.
    """
    if not compact_slots:
        return None
    slots = dict(compact_slots)
    upstream = slots.get("upstream_character_assigned", slots.get("UPSTREAM_CHARACTER_ASSIGNED", "UNKNOWN"))
    result = compose_local_sdxl_compact_prompt(
        upstream_character_assigned=upstream,
        character_id=slots.get("character_id") or slots.get("CHARACTER_ID"),
        environment=str(slots.get("environment") or slots.get("ENVIRONMENT") or ""),
        action=str(slots.get("action") or slots.get("ACTION") or ""),
        effect=str(slots.get("effect") or slots.get("EFFECT") or ""),
        effect_required=bool(slots.get("effect_required", True)),
        prop=str(slots.get("prop") or slots.get("PROP") or ""),
        prop_required=bool(slots.get("prop_required", True)),
        camera=str(slots.get("camera") or slots.get("CAMERA") or ""),
        lora_trigger=str(slots.get("lora_trigger") or slots.get("LORA_TRIGGER") or ""),
        path_id=PATH_ID,
    )
    return result.prompt
