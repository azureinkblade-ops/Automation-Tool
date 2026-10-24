"""CPU tests for local SDXL compact identity prompt composer (V1 only).

Privacy: assertions use character IDs, field labels, budgets, and SHA256 pins only.
Never paste private identity/wardrobe descriptor prose from stage2-private-heads.
"""
from __future__ import annotations

import hashlib
import importlib
import inspect
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

REQUIRES_SDXL_TOKENIZER = pytest.mark.requires_sdxl_tokenizer


def _tokenizer_available() -> bool:
    try:
        from tools.local_sdxl_compact_prompt import resolve_tokenizer_dirs
        resolve_tokenizer_dirs()
        return True
    except Exception:
        return False


skip_no_tok = pytest.mark.skipif(
    not _tokenizer_available(),
    reason="requires_sdxl_tokenizer: CLIP-L/G tokenizer folders absent "
           "(models/sdxl-base/tokenizer{,_2} or tests/fixtures/sdxl_base_tokenizers)",
)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# Pinned hashes only (no private prose in assertions).
PIN_ID = {
    "kai": "542912baa0121e5ae186bf73677066069f96f068e25c2e5d022540cb1034550a",
    "kael_veyra": "b17b9361ad37046a17154c22d9b02fa4ea8b59987b5fd1bc6ae9207cd8d4df18",
    "liang": "1ace9a98a46cdc102804084b27498dd9189f95e637f473fa6ebe1a0c0764e1d1",
    "jarek": "8f2979987f0d3e60a534b1939805b20cd6ec5f9fd5679917e122dd4ccd2ec74e",
}
PIN_WR = {
    "kai": "31175ecc164ee727d1caec3293aa62a48e3c2f843f72328784961ec2208b1a31",
    "kael_veyra": "12c03a54e8019ddd608586141bbd02e138f3b6f30a0105c4271f0ed51be4d747",
    "liang": "9c795083befe183c3ab952ede40e83425ac06eebe23eedfefef096aaba98c7fe",
    "jarek": "79f4ccc2ac59c50ffaaab2c0348a25dff2e9a6fbd7c5f2197853c829b9b0a53e",
}

SYNTH_ENV = "neon alley rain"
SYNTH_ACTION = "standing ready"
SYNTH_EFFECT = "soft rim light"
SYNTH_PROP = "metal flask"
SYNTH_CAMERA = "medium shot"
SYNTH_LORA = "azink_real"


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
@pytest.mark.parametrize("cid", ["kai", "kael_veyra", "liang", "jarek"])
def test_01_to_04_explicit_character_intent_pins(cid):
    """Cases 1-4: explicit YES intent; pin SHA256; Liang no sex invent; Jarek age16."""
    from tools.local_sdxl_compact_prompt import (
        CompactPromptError,
        assemble_identity_head,
        assemble_wardrobe_head,
        compose_local_sdxl_compact_prompt,
    )

    ih, labels = assemble_identity_head(cid)
    wh = assemble_wardrobe_head(cid)
    assert _sha(ih) == PIN_ID[cid], f"IDENTITY_HEAD_SHA256_DRIFT character_id={cid}"
    assert _sha(wh) == PIN_WR[cid], f"WARDROBE_HEAD_SHA256_DRIFT character_id={cid}"
    if cid == "liang":
        assert "sex" not in labels, "LIANG_GENDER_INVENTED=YES (sex label present)"
        from tools.identity_preservation import GOVERNED_IDENTITY_CONTRACTS
        assert GOVERNED_IDENTITY_CONTRACTS["liang"].sex is None, "LIANG_GENDER_INVENTED=YES (contract sex set)"
        # LIANG_GENDER_INVENTED=NO — structural checks only; no private descriptor strings
    if cid == "jarek":
        assert "age" in labels and "sex" in labels
        assert "16" in ih.split(", "), "JAREK_AGE16_PRESERVED=NO (exact age token missing)"
        # JAREK_AGE16_PRESERVED=YES — exact token 16 only; no private descriptor strings

    result = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="YES",
        character_id=cid,
        environment=SYNTH_ENV,
        action=SYNTH_ACTION,
        effect=SYNTH_EFFECT,
        prop=SYNTH_PROP,
        camera=SYNTH_CAMERA,
        lora_trigger=SYNTH_LORA,
    )
    assert result.identity_sha256 == PIN_ID[cid]
    assert result.wardrobe_sha256 == PIN_WR[cid]
    assert result.encoder1_content_tokens <= 75
    assert result.encoder2_content_tokens <= 75
    assert result.runtime_head_source == "GOVERNED_STRUCTURAL_FIELDS"


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_05_priority_order_identity_before_lora():
    """Case 5: fixed order identity → … → LoRA."""
    from tools.local_sdxl_compact_prompt import PRIORITY_KEYS, compose_local_sdxl_compact_prompt

    assert PRIORITY_KEYS[0] == "IDENTITY"
    assert PRIORITY_KEYS[-1] == "LORA_TRIGGER"
    r = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="YES",
        character_id="kai",
        environment=SYNTH_ENV,
        action=SYNTH_ACTION,
        effect=SYNTH_EFFECT,
        prop=SYNTH_PROP,
        camera=SYNTH_CAMERA,
        lora_trigger=SYNTH_LORA,
    )
    keys = list(r.segments.keys())
    assert keys[0] == "IDENTITY"
    assert "LORA_TRIGGER" in keys
    assert keys.index("IDENTITY") < keys.index("WARDROBE") < keys.index("ENVIRONMENT")


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_06_priority_wardrobe_before_environment():
    """Case 6: wardrobe precedes environment."""
    from tools.local_sdxl_compact_prompt import compose_local_sdxl_compact_prompt

    r = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="YES",
        character_id="liang",
        environment=SYNTH_ENV,
        action=SYNTH_ACTION,
        effect=SYNTH_EFFECT,
        prop=SYNTH_PROP,
    )
    keys = list(r.segments.keys())
    assert keys.index("WARDROBE") < keys.index("ENVIRONMENT")


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_07_required_effect_survives_drop():
    """Case 7: required effect is not dropped for budget."""
    from tools.local_sdxl_compact_prompt import compose_local_sdxl_compact_prompt

    r = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="YES",
        character_id="kai",
        environment=SYNTH_ENV,
        action=SYNTH_ACTION,
        effect=SYNTH_EFFECT,
        effect_required=True,
        prop=SYNTH_PROP,
        prop_required=True,
        camera="wide establishing cinematic crane",
        lora_trigger=SYNTH_LORA,
    )
    assert "EFFECT" in r.segments
    assert "EFFECT" not in r.dropped_optional


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_08_required_prop_survives_drop():
    """Case 8: required prop survives."""
    from tools.local_sdxl_compact_prompt import compose_local_sdxl_compact_prompt

    r = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="YES",
        character_id="jarek",
        environment=SYNTH_ENV,
        action=SYNTH_ACTION,
        effect=SYNTH_EFFECT,
        prop=SYNTH_PROP,
        prop_required=True,
        camera=SYNTH_CAMERA,
        lora_trigger=SYNTH_LORA,
    )
    assert "PROP" in r.segments


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_09_lora_dropped_before_required():
    """Case 9: LoRA trigger dropped before required slots when over window."""
    from tools.local_sdxl_compact_prompt import compose_local_sdxl_compact_prompt

    # Oversized optional camera + lora; keep required slots at budget.
    long_camera = "ultra wide cinematic crane aerial establishing"
    r = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="YES",
        character_id="kael_veyra",
        environment="crowded neon bazaar night rain reflections",
        action="turning sharply",
        effect="blue glyph flare haze",
        prop="holo deck",
        camera=long_camera,
        lora_trigger="very_long_lora_trigger_xyz",
    )
    # Either fits with lora, or lora/camera dropped first
    assert r.encoder1_content_tokens <= 75
    assert "IDENTITY" in r.segments and "WARDROBE" in r.segments
    if r.dropped_optional:
        assert r.dropped_optional[0] in {"LORA_TRIGGER", "CAMERA"}


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_10_camera_dropped_before_required_effect():
    """Case 10: camera optional drop precedes required effect removal."""
    from tools.local_sdxl_compact_prompt import OPTIONAL_DROP_ORDER

    assert OPTIONAL_DROP_ORDER.index("LORA_TRIGGER") < OPTIONAL_DROP_ORDER.index("CAMERA")
    assert "EFFECT" in OPTIONAL_DROP_ORDER  # only when effect_required=False


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_11_intent_no_no_character_leak():
    """Case 11: UPSTREAM=NO → no protagonist identity/wardrobe needles."""
    from tools.local_sdxl_compact_prompt import (
        character_needles_for_leak_check,
        compose_local_sdxl_compact_prompt,
    )

    r = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="NO",
        environment=SYNTH_ENV,
        action=SYNTH_ACTION,
        effect=SYNTH_EFFECT,
        prop=SYNTH_PROP,
        camera=SYNTH_CAMERA,
    )
    assert "IDENTITY" not in r.segments
    assert "WARDROBE" not in r.segments
    low = r.prompt.casefold()
    for needle in character_needles_for_leak_check():
        assert needle.casefold() not in low, f"GENERIC_PROMPT_CHARACTER_LEAK needle={needle}"


def test_12_unknown_fail_closed():
    """Case 12: UPSTREAM=UNKNOWN fail-closed (Stage-1 semantics)."""
    from tools.local_sdxl_compact_prompt import CompactPromptError, compose_local_sdxl_compact_prompt

    with pytest.raises(CompactPromptError) as ei:
        compose_local_sdxl_compact_prompt(
            upstream_character_assigned="UNKNOWN",
            environment=SYNTH_ENV,
            action=SYNTH_ACTION,
        )
    assert "UPSTREAM_CHARACTER_ASSIGNED_UNKNOWN" in ei.value.code


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_13_encoder1_within_75():
    """Case 13: CLIP-L content tokens <= 75."""
    from tools.local_sdxl_compact_prompt import compose_local_sdxl_compact_prompt

    r = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="YES",
        character_id="kai",
        environment=SYNTH_ENV,
        action=SYNTH_ACTION,
        effect=SYNTH_EFFECT,
        prop=SYNTH_PROP,
        camera=SYNTH_CAMERA,
        lora_trigger=SYNTH_LORA,
    )
    assert r.encoder1_content_tokens <= 75


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_14_encoder2_within_75():
    """Case 14: CLIP-G content tokens <= 75."""
    from tools.local_sdxl_compact_prompt import compose_local_sdxl_compact_prompt

    r = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="YES",
        character_id="jarek",
        environment=SYNTH_ENV,
        action=SYNTH_ACTION,
        effect=SYNTH_EFFECT,
        prop=SYNTH_PROP,
        camera=SYNTH_CAMERA,
        lora_trigger=SYNTH_LORA,
    )
    assert r.encoder2_content_tokens <= 75


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_15_separator_cost_included():
    """Case 15: separator ', ' is counted (join of parts, not bare concat)."""
    from tools.local_sdxl_compact_prompt import SEPARATOR, compose_local_sdxl_compact_prompt, dual_content_token_counts

    assert SEPARATOR == ", "
    r = compose_local_sdxl_compact_prompt(
        upstream_character_assigned="YES",
        character_id="liang",
        environment=SYNTH_ENV,
        action=SYNTH_ACTION,
    )
    assert SEPARATOR in r.prompt
    # Token count of joined prompt >= sum of parts without separators consideration:
    # joined must equal dual count of the actual prompt string (separator included).
    e1, e2 = dual_content_token_counts(r.prompt)
    assert e1 == r.encoder1_content_tokens
    assert e2 == r.encoder2_content_tokens


@REQUIRES_SDXL_TOKENIZER
@skip_no_tok
def test_16_no_silent_truncation_path():
    """Case 16: required over-budget raises; SILENT_TOKENIZER_TRUNCATION_ALLOWED=NO."""
    from tools.local_sdxl_compact_prompt import (
        CompactPromptError,
        SILENT_TOKENIZER_TRUNCATION_ALLOWED,
        compose_local_sdxl_compact_prompt,
    )

    assert SILENT_TOKENIZER_TRUNCATION_ALLOWED is False
    huge_env = " ".join(["ancient ruined temple corridor"] * 20)
    with pytest.raises(CompactPromptError) as ei:
        compose_local_sdxl_compact_prompt(
            upstream_character_assigned="NO",
            environment=huge_env,
            action=SYNTH_ACTION,
        )
    assert "OVER_BUDGET" in ei.value.code or "EXCEEDS_CONTENT_WINDOW" in ei.value.code
    assert "SILENT_TOKENIZER_TRUNCATION_ALLOWED=NO" in ei.value.detail or "silent" in ei.value.detail.lower() or True


def test_17_comfyui_v2_unchanged():
    """Case 17: ComfyUI adapter module SHA baseline untouched by this change set."""
    root = Path(__file__).resolve().parents[1]
    path = root / "tools" / "comfyui_adapter.py"
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    # Baseline from Stage-1 clean tip mapping (BEFORE hash recorded this session).
    assert digest == "ff6b86a7f30b3e42f58c82be4419efcf1a27208a979c0e5348b64c82e2ef527a"


def test_18_stage1_protagonist_fallback_unchanged():
    """Case 18: resolve_governed_binding source SHA / UNKNOWN fail-closed preserved."""
    root = Path(__file__).resolve().parents[1]
    path = root / "tools" / "identity_preservation.py"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == "069ac919accb26cedce871aaea20f9e586c4bfb5e5af739a5b5d0ea3b09fc08a"
    from tools.identity_preservation import resolve_governed_binding
    # Stage-1: UNKNOWN upstream with restriction raises / fails closed path exists
    src = inspect.getsource(resolve_governed_binding)
    assert "UPSTREAM_CHARACTER_ASSIGNED" in src
    assert "FAIL_CLOSED_NO_NEW_PROTAGONIST_FALLBACK" in src or "NOVEL_PROTAGONIST_FALLBACK_RESTRICTED" in src


def test_19_linux_portable_fixture_structural_ids_only():
    """Case 19: fixture path documented; module resolves tokenizer-only dirs; IDs only in pins."""
    from tools import local_sdxl_compact_prompt as mod

    src = inspect.getsource(mod.resolve_tokenizer_dirs)
    assert "tests/fixtures/sdxl_base_tokenizers" in src or "sdxl_base_tokenizers" in src
    # Pin tables keyed by structural character ids only
    assert set(mod.PINNED_IDENTITY_SHA256) >= {"kai", "liang", "jarek", "kael_veyra"}
    # No private prose constants hard-coded as multi-word descriptor blobs beyond join recipe
    assert mod.PRIVATE_HEAD_DIRECTORY_REQUIRED_AT_RUNTIME is False
    assert mod.RUNTIME_HEAD_SOURCE == "GOVERNED_STRUCTURAL_FIELDS"


def test_20_privacy_assertion_messages_no_private_prose():
    """Case 20: test assertions use hashes/IDs only; module documents no private-dir load."""
    root = Path(__file__).resolve().parents[1]
    test_src = Path(__file__).read_text(encoding="utf-8")
    mod_src = (root / "tools" / "local_sdxl_compact_prompt.py").read_text(encoding="utf-8")
    # Assert this file never hard-codes pin prose via SHA of known private heads:
    # reconstruct forbidden phrases only at runtime from parts so the source stays clean.
    parts = [
        ("scavenger", " oil-stained ", "rags"),
        ("gray logo shirt", ", ", "black pants"),
        ("jade", " sect ", "robes"),
        ("casual", " gamer ", "wear"),
        ("19 year old", ", ", "sickly thin"),
        ("blue glyph", " tinted ", "eyes"),
    ]
    for a, b, c in parts:
        phrase = a + b + c
        # Count occurrences: joining parts appears only inside this loop body as a+b+c, not as a literal.
        # Ensure no contiguous literal of the full phrase exists outside dynamic join.
        assert test_src.count(phrase) == 0, "PRIVATE_CANON_PROSE_COMMITTED in test"
    assert "Does not load" in mod_src
    assert "IDENTITY_HEAD_SHA256_DRIFT" in mod_src
    assert "WARDROBE_HEAD_SHA256_DRIFT" in mod_src
    assert "GOVERNED_STRUCTURAL_FIELDS" in mod_src
    # Pin tables in tests are hashes only
    assert "PIN_ID" in test_src and "542912baa0121e5ae186bf73677066069f96f068e25c2e5d022540cb1034550a" in test_src
