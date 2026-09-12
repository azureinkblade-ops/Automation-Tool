"""Local SDXL inpainting CLI for Stage 2 object refinement.

This is a model backend, not an app integration point. The CPU orchestration in
object_refinement.py owns feature gating, acceptance, and provenance.

Monolith boundary (EA4F-1): do not import app. Use gpu_runtime for path/DLL
bootstrap so this CLI stays subsystem-safe.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def composite_refinement(source: Any, generated: Any, mask: Any) -> Any:
    """Return generated pixels inside mask and exact source pixels outside it."""
    from PIL import Image

    return Image.composite(
        generated.convert("RGB"),
        source.convert("RGB"),
        mask.convert("L"),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local SDXL object refiner")
    parser.add_argument("--source", required=True)
    parser.add_argument("--mask", required=True)
    parser.add_argument("--guide", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--model", required=True)
    parser.add_argument("--lora", default="")
    parser.add_argument("--lora-scale", type=float, default=0.50)
    parser.add_argument("--seed", type=int, default=917364)
    parser.add_argument("--strength", type=float, default=0.25)
    parser.add_argument("--steps", type=int, default=35)
    parser.add_argument("--guidance-scale", type=float, default=7.0)
    parser.add_argument("--padding-mask-crop", type=int, default=64)
    return parser


def main() -> int:
    args = _parser().parse_args()

    # EA4F-1: bootstrap GPU/DLL paths without importing the monolith.
    try:
        from gpu_runtime import ensure_gpu_runtime

        ensure_gpu_runtime()
    except Exception:
        pass

    from PIL import Image
    import torch
    from diffusers import AutoPipelineForInpainting
    from local_image_generator import apply_scheduler

    source_path = Path(args.source)
    mask_path = Path(args.mask)
    guide_path = Path(args.guide) if args.guide else None
    output_path = Path(args.output)
    model_path = Path(args.model)
    lora_path = Path(args.lora) if args.lora else None
    for required in (source_path, mask_path, model_path):
        if not required.exists():
            raise SystemExit(f"missing prerequisite: {required}")
    if guide_path is not None and not guide_path.exists():
        raise SystemExit(f"missing guide: {guide_path}")
    if lora_path is not None and not lora_path.exists():
        raise SystemExit(f"missing LoRA: {lora_path}")
    if not (0.0 < args.strength <= 1.0):
        raise SystemExit("strength must be in (0, 1]")
    if args.steps < 1:
        raise SystemExit("steps must be >= 1")

    source = Image.open(source_path).convert("RGB")
    mask = Image.open(mask_path).convert("L")
    initial = Image.open(guide_path).convert("RGB") if guide_path else source
    if source.size != mask.size or source.size != initial.size:
        raise SystemExit("source, mask, and optional guide dimensions must match")
    if mask.getbbox() is None:
        raise SystemExit("mask has no authorized pixels")

    pipe = AutoPipelineForInpainting.from_pretrained(
        str(model_path),
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
        local_files_only=True,
    )
    pipe = apply_scheduler(pipe, "dpm")
    if lora_path is not None:
        pipe.load_lora_weights(str(lora_path.parent), weight_name=lora_path.name)
        try:
            pipe.fuse_lora(lora_scale=args.lora_scale)
        except Exception:
            pass
    pipe = pipe.to("cuda")
    try:
        pipe.enable_attention_slicing()
        pipe.enable_vae_slicing()
    except Exception:
        pass

    generator = torch.Generator(device="cuda").manual_seed(args.seed)
    with torch.no_grad():
        generated = pipe(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            image=initial,
            mask_image=mask,
            num_inference_steps=args.steps,
            guidance_scale=args.guidance_scale,
            strength=args.strength,
            generator=generator,
            padding_mask_crop=args.padding_mask_crop,
        ).images[0]

    candidate = composite_refinement(source, generated, mask)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidate.save(output_path)
    metadata = {
        "schema_version": 1,
        "model": str(model_path),
        "seed": args.seed,
        "parameters": {
            "strength": args.strength,
            "steps": args.steps,
            "guidance_scale": args.guidance_scale,
            "padding_mask_crop": args.padding_mask_crop,
            "lora_path": str(lora_path) if lora_path else None,
            "lora_scale": args.lora_scale if lora_path else None,
            "guide_path": str(guide_path) if guide_path else None,
        },
    }
    sidecar = output_path.with_suffix(output_path.suffix + ".refinement.json")
    sidecar.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
