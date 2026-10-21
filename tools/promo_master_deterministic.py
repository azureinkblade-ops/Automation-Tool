"""Promo Master Phase 4A: deterministic non-generative finishing (CPU only).

Downstream of V2 generation. Does not alter Studio Bible, novel-id
normalization, prompt projection, camera/lighting policy, or checkpoint routing.

Pipeline: Lanczos resize 1024 -> 2048, then one conservative unsharp mask.
No learned weights, no ComfyUI, no GPU.

Neural 4x candidates remain frozen and unused by this module.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import FrozenSet, Iterable, Set, Tuple

from PIL import Image, ImageFilter

INPUT_EXPECTED = (1024, 1024)
FINAL_OUTPUT = (2048, 2048)
RESIZE_METHOD = "lanczos"
SHARPEN_METHOD = "unsharp_mask"
SHARPEN_RADIUS = 1.0
SHARPEN_AMOUNT = 50  # Pillow UnsharpMask percent
SHARPEN_THRESHOLD = 3

NEW_SEMANTIC_OBJECTS_REQUIRED = 0
HAND_OBJECT_SENTINEL = (
    "viewer-left hand must remain empty if empty in source; "
    "viewer-right hand must not acquire an object"
)
PRESERVATION_GATES: Tuple[str, ...] = (
    "CHARACTER_IDENTITY",
    "WARDROBE",
    "COMPOSITION",
    "FACE_ANATOMY",
    "HAND_ANATOMY",
    "HAIR_STRUCTURE",
    "EXISTING_SUPERNATURAL_EFFECTS",
    "ENVIRONMENT_OBJECTS",
    "NEW_SEMANTIC_OBJECTS",
)

SEALED_SOURCE_PATH = Path(
    r"C:\Users\David\Documents\Automation tool\output"
    r"\studio-bible-production-path-20260908\HA-photorealistic-realvisxl.png"
)
SEALED_SOURCE_SHA256 = (
    "9a1ad7d4b55f5aa8554c04312b0602ced32946dc24cf6056fb3f130d77299797"
)

QUALIFICATION_MASTER_AUTHORIZED = False
GPU_AUTHORIZED = False

CPU_ONLY_ALLOWED_IMPORT_ROOTS: FrozenSet[str] = frozenset(
    {"__future__", "ast", "re", "pathlib", "typing", "PIL"}
)
CPU_ONLY_DENY_IMPORT_ROOTS: FrozenSet[str] = frozenset(
    {
        "torch",
        "comfy",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "http",
        "socket",
        "importlib",
    }
)
CPU_ONLY_DENY_NAMES: FrozenSet[str] = frozenset(
    {
        "UpscaleModelLoader",
        "ImageUpscaleWithModel",
        "KSampler",
        "CheckpointLoader",
        "CLIPTextEncode",
        "CLIP",
        "ControlNet",
        "IPAdapter",
        "LoraLoader",
        "FaceDetailer",
    }
)
CPU_ONLY_DENY_STRINGS: FrozenSet[str] = frozenset(
    {"/prompt", "UpscaleModelLoader", "ImageUpscaleWithModel", "KSampler"}
)
_POLICY_NAME_RE = re.compile(r"(deny|prohibit|forbidden|policy|allowed)", re.I)


class DeterministicPromoMasterError(RuntimeError):
    """CPU finishing contract failed."""


def _string_constants(node: ast.AST) -> Set[str]:
    found: Set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            found.add(child.value)
    return found


def _policy_strings(tree: ast.AST) -> Set[str]:
    allowed: Set[str] = set()
    body = tree.body if isinstance(tree, ast.Module) else []
    for node in body:
        target_names: Iterable[str] = ()
        value = None
        if isinstance(node, ast.Assign):
            target_names = (
                t.id for t in node.targets if isinstance(t, ast.Name)
            )
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = (node.target.id,)
            value = node.value
        if value is None:
            continue
        if not any(_POLICY_NAME_RE.search(name) for name in target_names):
            continue
        allowed.update(_string_constants(value))
    return allowed


def _import_roots(tree: ast.AST) -> Set[str]:
    roots: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def validate_cpu_only_source(source: str) -> None:
    """AST-inspect operational code. Deny-list string literals are not uses."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise DeterministicPromoMasterError(f"unparseable source: {exc}") from exc
    policy = _policy_strings(tree)
    for root in _import_roots(tree):
        if root in CPU_ONLY_DENY_IMPORT_ROOTS or root not in CPU_ONLY_ALLOWED_IMPORT_ROOTS:
            raise DeterministicPromoMasterError(f"prohibited import root: {root}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"__import__", "eval", "exec"}:
                raise DeterministicPromoMasterError(f"prohibited call: {func.id}")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in CPU_ONLY_DENY_NAMES:
                raise DeterministicPromoMasterError(f"prohibited name: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in CPU_ONLY_DENY_NAMES:
            raise DeterministicPromoMasterError(f"prohibited attribute: {node.attr}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in CPU_ONLY_DENY_STRINGS and node.value not in policy:
                raise DeterministicPromoMasterError(
                    f"prohibited operational string: {node.value}"
                )


def assert_this_module_cpu_only() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    validate_cpu_only_source(text)


def runtime_import_roots() -> Tuple[str, ...]:
    text = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    return tuple(sorted(_import_roots(tree)))


def finish_image(image: Image.Image) -> Image.Image:
    """Return a 2048 RGB/RGBA master. Does not write disk. Does not load models."""
    if QUALIFICATION_MASTER_AUTHORIZED:
        raise DeterministicPromoMasterError("qualification master flag must stay false in 4A")
    if GPU_AUTHORIZED:
        raise DeterministicPromoMasterError("GPU flag must stay false")
    if image.size != INPUT_EXPECTED:
        raise DeterministicPromoMasterError(
            f"expected {INPUT_EXPECTED}, got {image.size}"
        )
    mode = image.mode
    if mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
        mode = "RGB"
    resized = image.resize(FINAL_OUTPUT, Image.Resampling.LANCZOS)
    mask = ImageFilter.UnsharpMask(
        radius=SHARPEN_RADIUS,
        percent=SHARPEN_AMOUNT,
        threshold=SHARPEN_THRESHOLD,
    )
    if mode == "RGBA":
        rgb = resized.convert("RGB").filter(mask)
        alpha = resized.getchannel("A")
        out = Image.merge("RGBA", (*rgb.split(), alpha))
    else:
        out = resized.filter(mask)
    if out.size != FINAL_OUTPUT:
        raise DeterministicPromoMasterError("final size is not 2048x2048")
    return out


def pixels_of(image: Image.Image) -> bytes:
    """Raw pixel bytes used for PIXEL_IDENTICAL checks. No PNG container."""
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    return image.tobytes()


def save_png(image: Image.Image, path: Path) -> None:
    """Write PNG without extra metadata. Encoder zlib settings are fixed.

    Pixel identity is the contract. PNG byte identity is not guaranteed across
    Pillow/zlib builds because the container can still differ.
    """
    path = Path(path)
    image.save(
        path,
        format="PNG",
        compress_level=6,
        optimize=False,
        pnginfo=None,
    )
