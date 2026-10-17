"""Effective-prompt measurement for the production SDXL text path (R2 Parts E/F/M).

Production local renderer (local_image_generator.py -> diffusers SDXL pipeline loaded from
LOCAL_SD_MODEL=models\\sdxl-base) tokenizes with CLIPTokenizer(model_max_length=77,
truncation=True): BOS + 75 content tokens + EOS reach the text encoders; the rest is dropped.

This module re-implements the CLIP byte-level BPE (openai/CLIP simple_tokenizer, as used by
transformers CLIPTokenizer) in pure Python using the SAME vocab.json / merges.txt shipped in
models/sdxl-base/tokenizer, so the app process can record EFFECTIVE_PROMPT_HASH without torch /
transformers. Parity against transformers.CLIPTokenizer is verified in the R2 evidence.
Read-only: never writes, never downloads.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CLIP_MAX_LENGTH = 77            # model_max_length incl. BOS + EOS
CLIP_CONTENT_TOKENS = CLIP_MAX_LENGTH - 2  # 75 retained content tokens

_ROOT = Path(__file__).resolve().parent.parent

try:  # same pattern as transformers CLIPTokenizer (uses the `regex` module)
    import regex as _rx  # type: ignore
    _PAT = _rx.compile(
        r"""<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[\p{L}]+|[\p{N}]|[^\s\p{L}\p{N}]+""",
        _rx.IGNORECASE,
    )
    PATTERN_ENGINE = "regex"
except Exception:  # pragma: no cover - fallback approximation of \p{L} / \p{N}
    _PAT = re.compile(
        r"""<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[^\W\d_]+|\d|(?:[^\s\w]|_)+""",
        re.IGNORECASE,
    )
    PATTERN_ENGINE = "re_fallback"


def _bytes_to_unicode() -> Dict[int, str]:
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("\xa1"), ord("\xac") + 1)) + list(
        range(ord("\xae"), ord("\xff") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))


def _tokenizer_dir() -> Optional[Path]:
    cands: List[Path] = []
    env_model = os.environ.get("LOCAL_SD_MODEL", "").strip()
    if env_model:
        p = Path(env_model)
        cands.append((p if p.is_absolute() else _ROOT / p) / "tokenizer")
    cands.append(_ROOT / "models" / "sdxl-base" / "tokenizer")
    for c in cands:
        if (c / "vocab.json").exists() and (c / "merges.txt").exists():
            return c
    return None


@lru_cache(maxsize=1)
def _load() -> Optional[Tuple[Dict[str, int], Dict[Tuple[str, str], int], str]]:
    d = _tokenizer_dir()
    if d is None:
        return None
    encoder = json.loads((d / "vocab.json").read_text(encoding="utf-8"))
    merges = (d / "merges.txt").read_text(encoding="utf-8").strip().split("\n")[1: 49152 - 256 - 2 + 1]
    ranks = {tuple(m.split()): i for i, m in enumerate(merges)}
    return encoder, ranks, str(d)


def tokenizer_source() -> str:
    data = _load()
    return f"pure_python_clip_bpe:{data[2]}:{PATTERN_ENGINE}" if data else "UNAVAILABLE"


_BYTE_ENCODER = _bytes_to_unicode()


def _clean(text: str) -> str:
    # transformers CLIPTokenizer without ftfy: BasicTokenizer(do_lower_case, no punct split)
    # + whitespace clean + lower. html.unescape mirrors CLIP basic_clean.
    t = html.unescape(html.unescape(str(text or "")))
    t = "".join(ch for ch in t if not (ord(ch) == 0 or ord(ch) == 0xFFFD or (ord(ch) < 32 and ch not in "\t\n\r")))
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower()


@lru_cache(maxsize=20000)
def _bpe(token: str) -> Tuple[str, ...]:
    data = _load()
    assert data is not None
    ranks = data[1]
    word = tuple(token[:-1]) + (token[-1] + "</w>",)
    pairs = {(word[i], word[i + 1]) for i in range(len(word) - 1)}
    if not pairs:
        return (token + "</w>",)
    while True:
        bigram = min(pairs, key=lambda p: ranks.get(p, float("inf")))
        if bigram not in ranks:
            break
        first, second = bigram
        new_word: List[str] = []
        i = 0
        while i < len(word):
            try:
                j = word.index(first, i)
            except ValueError:
                new_word.extend(word[i:])
                break
            new_word.extend(word[i:j])
            i = j
            if word[i] == first and i < len(word) - 1 and word[i + 1] == second:
                new_word.append(first + second)
                i += 2
            else:
                new_word.append(word[i])
                i += 1
        word = tuple(new_word)
        if len(word) == 1:
            break
        pairs = {(word[i], word[i + 1]) for i in range(len(word) - 1)}
    return word


def clip_token_ids(text: Any) -> Optional[List[int]]:
    """Content token ids (no BOS/EOS) or None when the tokenizer files are unavailable."""
    data = _load()
    if data is None:
        return None
    encoder = data[0]
    ids: List[int] = []
    for tok in _PAT.findall(_clean(str(text or ""))):
        tok = "".join(_BYTE_ENCODER[b] for b in tok.encode("utf-8"))
        for piece in _bpe(tok):
            if piece in encoder:
                ids.append(encoder[piece])
    return ids


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def effective_prompt(text: Any, max_length: int = CLIP_MAX_LENGTH) -> Dict[str, Any]:
    """FULL / EFFECTIVE prompt hashes for the 77-token CLIP window (BOS+75+EOS)."""
    s = str(text or "")
    ids = clip_token_ids(s)
    content_max = max_length - 2
    if ids is None:
        words = s.split()
        kept = " ".join(words[:content_max])
        return {
            "FULL_PROMPT_HASH": _sha(s),
            "EFFECTIVE_PROMPT_HASH": _sha("WORDS:" + kept),
            "EFFECTIVE_PROMPT_TOKEN_COUNT": min(len(words), content_max),
            "FULL_PROMPT_TOKEN_COUNT": len(words),
            "EFFECTIVE_PROMPT_TRUNCATED": len(words) > content_max,
            "EFFECTIVE_PROMPT_TOKENIZER": "UNAVAILABLE_WORD_APPROX",
            "EFFECTIVE_PROMPT_IDS": [],
        }
    kept_ids = ids[:content_max]
    return {
        "FULL_PROMPT_HASH": _sha(s),
        "EFFECTIVE_PROMPT_HASH": _sha("CLIP77:" + ",".join(str(i) for i in kept_ids)),
        "EFFECTIVE_PROMPT_TOKEN_COUNT": len(kept_ids),
        "FULL_PROMPT_TOKEN_COUNT": len(ids),
        "EFFECTIVE_PROMPT_TRUNCATED": len(ids) > content_max,
        "EFFECTIVE_PROMPT_TOKENIZER": tokenizer_source(),
        "EFFECTIVE_PROMPT_IDS": kept_ids,
    }


def decode_ids(ids: List[int]) -> str:
    data = _load()
    if data is None:
        return ""
    dec = {v: k for k, v in data[0].items()}
    byte_dec = {v: k for k, v in _BYTE_ENCODER.items()}
    text = "".join(dec.get(i, "") for i in ids).replace("</w>", " ")
    out = bytearray()
    for c in text:
        if c == " ":
            out.append(32)
        elif c in byte_dec:
            out.append(byte_dec[c])
    return out.decode("utf-8", errors="replace").strip()


def effective_prompt_text(text: Any, max_length: int = CLIP_MAX_LENGTH) -> str:
    ids = clip_token_ids(text)
    if ids is None:
        return " ".join(str(text or "").split()[: max_length - 2])
    return decode_ids(ids[: max_length - 2])
