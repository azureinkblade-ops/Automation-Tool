from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def clamp_dimension(value: int) -> int:
    value = max(256, min(int(value), 1536))
    return value - (value % 8)


def quality_defaults(mode: str) -> dict[str, float | int]:
    mode = (mode or "balanced").strip().lower()
    if mode == "fast":
        return {"steps": 18, "guidance_scale": 6.0, "refiner_strength": 0.0}
    if mode == "premium":
        return {"steps": 40, "guidance_scale": 7.0, "refiner_strength": 0.25}
    if mode == "draft":
        return {"steps": 12, "guidance_scale": 5.5, "refiner_strength": 0.0}
    return {"steps": 26, "guidance_scale": 6.5, "refiner_strength": 0.0}


def is_sdxl_model(model: str) -> bool:
    lowered = (model or "").lower()
    return "xl" in lowered or "sdxl" in lowered


def scheduler_name(value: str) -> str:
    return (value or "").strip().lower().replace("_", "-")


def apply_scheduler(pipe, name: str):
    name = scheduler_name(name)
    if not name or name in {"default", "model"}:
        return pipe
    try:
        if name in {"dpm", "dpm++", "dpm-solver", "dpm-solver++"}:
            from diffusers import DPMSolverMultistepScheduler

            pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
        elif name in {"euler", "euler-discrete"}:
            from diffusers import EulerDiscreteScheduler

            pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config)
        elif name in {"euler-a", "euler-ancestral"}:
            from diffusers import EulerAncestralDiscreteScheduler

            pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
        elif name in {"ddim"}:
            from diffusers import DDIMScheduler

            pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config)
    except Exception:
        # Scheduler choice should not make the whole fallback unusable.
        return pipe
    return pipe


def load_input_image(path: str, width: int, height: int):
    if not path:
        return None
    from PIL import Image

    image = Image.open(path).convert("RGB")
    image.thumbnail((width, height))
    canvas = Image.new("RGB", (width, height), (8, 10, 14))
    offset = ((width - image.width) // 2, (height - image.height) // 2)
    canvas.paste(image, offset)
    return canvas


def resolve_metadata_target(value: str, output: Path) -> tuple[Path, dict[str, object]]:
    value = (value or "").strip()
    if not value:
        return output.with_suffix(output.suffix + ".local-sd.json"), {}
    if value.startswith("{"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return output.with_suffix(output.suffix + ".local-sd.json"), parsed
        except json.JSONDecodeError:
            parsed = parse_loose_metadata_object(value)
            if parsed:
                return output.with_suffix(output.suffix + ".local-sd.json"), parsed
    return Path(value).resolve(), {}


def parse_loose_metadata_object(value: str) -> dict[str, object]:
    text = value.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return {}
    result: dict[str, object] = {}
    for part in text[1:-1].split(","):
        if ":" not in part:
            return {}
        key, raw_value = part.split(":", 1)
        key = key.strip().strip("\"'")
        raw_value = raw_value.strip().strip("\"'")
        if not key:
            return {}
        if raw_value.lower() in {"true", "false"}:
            result[key] = raw_value.lower() == "true"
        else:
            try:
                result[key] = int(raw_value)
            except ValueError:
                try:
                    result[key] = float(raw_value)
                except ValueError:
                    result[key] = raw_value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a local Stable Diffusion image for the Automation Tool.")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--model", default=os.environ.get("LOCAL_SD_MODEL", "stabilityai/stable-diffusion-xl-base-1.0"))
    parser.add_argument("--refiner-model", default=os.environ.get("LOCAL_SD_REFINER_MODEL", ""))
    parser.add_argument("--quality-mode", default=os.environ.get("LOCAL_SD_QUALITY_MODE", "premium"))
    parser.add_argument("--scheduler", default=os.environ.get("LOCAL_SD_SCHEDULER", "dpm"))
    parser.add_argument("--input-image", default="")
    parser.add_argument("--strength", type=float, default=float(os.environ.get("LOCAL_SD_IMG2IMG_STRENGTH", "0.52")))
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=1344)
    parser.add_argument("--steps", type=int, default=0)
    parser.add_argument("--guidance-scale", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--lora-path", default=os.environ.get("LOCAL_SD_LORA_PATH", ""))
    parser.add_argument("--lora-scale", type=float, default=float(os.environ.get("LOCAL_SD_LORA_SCALE", "0.75")))
    parser.add_argument("--metadata", default="")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path, extra_metadata = resolve_metadata_target(args.metadata, output)

    try:
        import torch
        from diffusers import AutoPipelineForImage2Image, AutoPipelineForText2Image, DiffusionPipeline, StableDiffusionPipeline
    except Exception as exc:
        raise RuntimeError(
            "Local Stable Diffusion dependencies are not installed. Install torch, diffusers, transformers, and pillow."
        ) from exc

    width = clamp_dimension(args.width)
    height = clamp_dimension(args.height)
    defaults = quality_defaults(args.quality_mode)
    steps = max(8, min(int(args.steps or defaults["steps"]), 80))
    guidance_scale = float(args.guidance_scale or defaults["guidance_scale"])
    strength = max(0.1, min(float(args.strength), 0.95))
    started = time.time()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    if device == "cuda":
        try:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
        except Exception:
            pass
    model = args.model
    input_image = load_input_image(args.input_image, width, height) if args.input_image else None

    if input_image:
        pipe = AutoPipelineForImage2Image.from_pretrained(model, torch_dtype=dtype)
    elif is_sdxl_model(model):
        pipe = AutoPipelineForText2Image.from_pretrained(model, torch_dtype=dtype, variant="fp16" if device == "cuda" else None, use_safetensors=True)
    else:
        pipe = StableDiffusionPipeline.from_pretrained(model, torch_dtype=dtype)
    pipe = apply_scheduler(pipe, args.scheduler)
    lora_loaded = False
    lora_error = ""
    lora_path = Path(args.lora_path).resolve() if args.lora_path else None
    if lora_path and lora_path.exists():
        try:
            pipe.load_lora_weights(str(lora_path.parent), weight_name=lora_path.name)
            try:
                pipe.fuse_lora(lora_scale=float(args.lora_scale))
            except Exception:
                pass
            lora_loaded = True
        except Exception as exc:
            lora_error = str(exc)
            if os.environ.get("LOCAL_SD_LORA_STRICT", "0").strip().lower() in {"1", "true", "yes", "on"}:
                raise
    pipe = pipe.to(device)
    if device == "cuda":
        xformers_enabled = False
        if os.environ.get("LOCAL_SD_XFORMERS", "1").strip().lower() not in {"0", "false", "no", "off"}:
            try:
                pipe.enable_xformers_memory_efficient_attention()
                xformers_enabled = True
            except Exception:
                xformers_enabled = False
        try:
            if not xformers_enabled:
                pipe.enable_attention_slicing()
        except Exception:
            pass
        try:
            pipe.enable_vae_slicing()
        except Exception:
            pass
        try:
            pipe.unet.to(memory_format=torch.channels_last)
        except Exception:
            pass
    else:
        xformers_enabled = False

    generator = None
    if args.seed:
        generator = torch.Generator(device=device).manual_seed(args.seed)

    with torch.no_grad():
        common = {
            "prompt": args.prompt,
            "negative_prompt": args.negative_prompt or None,
            "num_inference_steps": steps,
            "guidance_scale": guidance_scale,
            "generator": generator,
        }
        if input_image:
            result = pipe(image=input_image, strength=strength, **common)
        else:
            result = pipe(width=width, height=height, **common)

    image = result.images[0]
    refiner_used = False
    refiner_strength = float(defaults["refiner_strength"])
    if args.refiner_model and refiner_strength > 0 and is_sdxl_model(model):
        try:
            refiner = DiffusionPipeline.from_pretrained(
                args.refiner_model,
                torch_dtype=dtype,
                variant="fp16" if device == "cuda" else None,
                use_safetensors=True,
            ).to(device)
            refined = refiner(
                prompt=args.prompt,
                negative_prompt=args.negative_prompt or None,
                image=image,
                num_inference_steps=max(8, min(int(steps * refiner_strength), 24)),
                generator=generator,
            )
            image = refined.images[0]
            refiner_used = True
        except Exception:
            refiner_used = False
    image.save(output)
    metadata = {
        "provider": "local_stable_diffusion",
        "model": model,
        "refinerModel": args.refiner_model,
        "refinerUsed": refiner_used,
        "qualityMode": args.quality_mode,
        "scheduler": args.scheduler,
        "device": device,
        "xformers": xformers_enabled,
        "width": width,
        "height": height,
        "steps": steps,
        "guidanceScale": guidance_scale,
        "inputImage": args.input_image,
        "strength": strength if input_image else 0,
        "seed": args.seed,
        "loraPath": str(lora_path) if lora_path else "",
        "loraLoaded": lora_loaded,
        "loraScale": args.lora_scale,
        "loraError": lora_error,
        "seconds": round(time.time() - started, 2),
        "prompt": args.prompt,
        "negativePrompt": args.negative_prompt,
        "output": str(output),
    }
    metadata.update(extra_metadata)
    try:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        metadata["metadataPath"] = str(metadata_path)
    except OSError as exc:
        metadata["metadataWarning"] = f"Image was created, but metadata could not be written: {exc}"
    print(json.dumps(metadata))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
