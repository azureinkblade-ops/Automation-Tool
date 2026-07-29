"""Track 4 T3: evidence-only localized jian inpainting fallback.

Uses frozen Map-B seed 917364 output as source. Inpaints only the verified
outer-hip/robe mask. Same local SDXL base and azink_main LoRA 0.50.
No production, registry, Map B, or feature-flag edits.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import app as appmod  # establish the correct GPU/PIL import path

from PIL import Image
import numpy as np
import torch
from diffusers import AutoPipelineForInpainting
from local_image_generator import apply_scheduler
import tests.render_ab.harness as H

SRC = ROOT / "tests" / "render_ab" / "output" / "map_compare_B" / "917364" / "D.png"
INIT = ROOT / "tests" / "render_ab" / "output" / "track4_inpaint" / "seed917364_jian_guide.png"
MASK = ROOT / "tests" / "render_ab" / "output" / "track4_inpaint" / "seed917364_jian_mask.png"
OUT_DIR = ROOT / "tests" / "render_ab" / "output" / "track4_inpaint"
OUT = OUT_DIR / "seed917364_jian_inpaint_guided_v2.png"
META = OUT_DIR / "seed917364_jian_inpaint_guided_v2.json"
MODEL = ROOT / "models" / "sdxl-base"
LORA = ROOT / "loras" / "main-posts" / "pytorch_lora_weights.safetensors"
SEED = 917364
LORA_SCALE = 0.50


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    for p in (SRC, INIT, MASK, MODEL, LORA):
        if not p.exists():
            raise SystemExit(f"missing prerequisite: {p}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    phrases = [
        "Liang enters the ruined sect hall",
        "He climbs the broken stair toward the jade altar",
        "Silver light wakes the dormant formation",
    ]
    frozen = H.capture_prompts(
        "The Hundredfold Path", "chapter text", phrases, "hp", appmod
    )["director"][2]
    prompt = (
        frozen
        + ". LOCAL INPAINT ONLY: at Liang's outer left hip, add one unmistakable "
          "standard-length Chinese jian in a dark teal scabbard, simple silver guard "
          "and visible hilt, hanging naturally along the outer robe; preserve the robe, "
          "hands, kneeling pose, face, body, and background unchanged."
    )
    negative = (
        "extra person, female, standing, duplicate sword, multiple weapons, staff, spear, "
        "polearm, oversized weapon, floating weapon, ribbon, sash, rope, tassel, fabric strip, "
        "malformed hand, extra fingers, text, watermark"
    )

    source_image = Image.open(SRC).convert("RGB")
    image = Image.open(INIT).convert("RGB")
    mask = Image.open(MASK).convert("L")
    if source_image.size != image.size or image.size != mask.size:
        raise SystemExit(
            f"source/init/mask mismatch: {source_image.size} vs {image.size} vs {mask.size}"
        )

    dtype = torch.float16
    pipe = AutoPipelineForInpainting.from_pretrained(
        str(MODEL), torch_dtype=dtype, variant="fp16", use_safetensors=True,
        local_files_only=True,
    )
    pipe = apply_scheduler(pipe, "dpm")
    pipe.load_lora_weights(str(LORA.parent), weight_name=LORA.name)
    try:
        pipe.fuse_lora(lora_scale=LORA_SCALE)
    except Exception:
        pass
    pipe = pipe.to("cuda")
    try:
        pipe.enable_attention_slicing()
        pipe.enable_vae_slicing()
    except Exception:
        pass

    generator = torch.Generator(device="cuda").manual_seed(SEED)
    with torch.no_grad():
        result = pipe(
            prompt=prompt,
            negative_prompt=negative,
            image=image,
            mask_image=mask,
            num_inference_steps=35,
            guidance_scale=7.0,
            strength=0.25,
            generator=generator,
            padding_mask_crop=64,
        ).images[0]
    result.save(OUT)

    # Verify non-mask preservation numerically. Ignore feathered pixels where mask > 0.
    src = np.asarray(source_image).astype(np.int16)
    dst = np.asarray(result.convert("RGB")).astype(np.int16)
    m = np.asarray(mask)
    outside = m == 0
    absdiff = np.abs(src - dst)
    outside_mean = float(absdiff[outside].mean()) if outside.any() else None
    outside_max = int(absdiff[outside].max()) if outside.any() else None

    metadata = {
        "experiment": "track4_t3_local_inpaint",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(SRC),
        "source_sha256": sha256(SRC),
        "guided_init": str(INIT),
        "guided_init_sha256": sha256(INIT),
        "mask": str(MASK),
        "mask_sha256": sha256(MASK),
        "output": str(OUT),
        "output_sha256": sha256(OUT),
        "model": str(MODEL),
        "lora": str(LORA),
        "lora_scale": LORA_SCALE,
        "seed": SEED,
        "steps": 35,
        "guidance_scale": 7.0,
        "strength": 0.25,
        "padding_mask_crop": 64,
        "outside_mask_absdiff_mean": outside_mean,
        "outside_mask_absdiff_max": outside_max,
        "scope": "evidence-only; no production/registry/Map-B edits",
    }
    META.write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
